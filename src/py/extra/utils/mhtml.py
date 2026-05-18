import re
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from email.message import Message
from pathlib import Path
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit


RE_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


@dataclass(slots=True)
class MHTMLPart:
	contentType: str
	location: str | None
	virtualPath: str | None
	payload: bytes
	charset: str | None = None

	def text(self) -> str | None:
		if not self.contentType.startswith("text/"):
			return None
		encoding = self.charset or "utf-8"
		try:
			return self.payload.decode(encoding, errors="replace")
		except LookupError:
			return self.payload.decode("utf-8", errors="replace")


@dataclass(slots=True)
class MHTMLDocument:
	parts: list[MHTMLPart]
	root: MHTMLPart
	byVirtualPath: dict[str, MHTMLPart]
	origin: str | None = None

	def replacements(self, baseRoute: str) -> dict[str, str]:
		res: dict[str, str] = {}
		for part in self.parts:
			if part is self.root:
				continue
			if not part.location or not part.virtualPath:
				continue
			mapped = f"/{baseRoute}/{part.virtualPath}".replace("//", "/")
			for key in self.LocationVariants(part.location):
				res[key] = mapped
		return res

	def render(self, baseRoute: str) -> str:
		ordered = self._orderedReplacements(baseRoute)
		for part in self.parts:
			text = part.text()
			if text is None:
				continue
			text = self._rewriteText(text, ordered)
			if part is self.root:
				return text
		root_text = self.root.text()
		return root_text or self.root.payload.decode("utf-8", errors="replace")

	def payloadFor(self, part: MHTMLPart, baseRoute: str) -> bytes:
		text = part.text()
		if text is None:
			return part.payload
		rewritten = self._rewriteText(text, self._orderedReplacements(baseRoute))
		encoding = part.charset or "utf-8"
		try:
			return rewritten.encode(encoding, errors="replace")
		except LookupError:
			return rewritten.encode("utf-8", errors="replace")

	def _orderedReplacements(self, baseRoute: str) -> list[tuple[str, str]]:
		mapping = self.replacements(baseRoute)
		return sorted(mapping.items(), key=lambda kv: len(kv[0]), reverse=True)

	def _rewriteText(self, text: str, replacements: list[tuple[str, str]]) -> str:
		if not replacements:
			return text
		mapping = {src: dst for src, dst in replacements}
		pattern = re.compile(
			"|".join(re.escape(src) for src, _ in replacements)
		)
		return pattern.sub(lambda m: mapping.get(m.group(0), m.group(0)), text)

	def fallbackURL(self, subpath: str) -> str | None:
		if not self.origin:
			return None
		clean = "/" + subpath.lstrip("/")
		return f"{self.origin}{clean}"

	@classmethod
	def Parse(cls, path: Path) -> "MHTMLDocument":
		message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
		parts: list[MHTMLPart] = []
		for m in cls.IterPayloadParts(message):
			location = m.get("Content-Location")
			ctype = m.get_content_type()
			charset = m.get_content_charset()
			payload = m.get_payload(decode=True)
			if payload is None:
				content = m.get_payload()
				payload = content.encode("utf-8") if isinstance(content, str) else b""
			parts.append(
				MHTMLPart(
					contentType=ctype,
					location=location,
					virtualPath=cls.VirtualPathFromLocation(location),
					payload=payload,
					charset=charset,
				)
			)
		if not parts:
			raise ValueError(f"No MIME parts found in MHTML document: {path}")
		root = next((p for p in parts if p.contentType == "text/html"), parts[0])
		root_location = root.location or ""
		root_url = urlsplit(root_location) if root_location else None
		origin = (
			f"{root_url.scheme}://{root_url.netloc}"
			if root_url and root_url.scheme and root_url.netloc
			else None
		)
		by_path: dict[str, MHTMLPart] = {}
		for part in parts:
			if not part.virtualPath:
				continue
			by_path[part.virtualPath] = part
		return cls(parts=parts, root=root, byVirtualPath=by_path, origin=origin)

	@staticmethod
	def IterPayloadParts(message: Message) -> list[Message]:
		if not message.is_multipart():
			return [message]
		return [p for p in message.walk() if not p.is_multipart()]

	@staticmethod
	def NormalizePath(path: str) -> str:
		clean = path.split("#", 1)[0].split("?", 1)[0].strip()
		if not clean:
			return ""
		parts = [
			p
			for p in PurePosixPath(unquote(clean)).parts
			if p not in ("", ".", "..", "/")
		]
		return "/".join(parts)

	@classmethod
	def VirtualPathFromLocation(cls, location: str | None) -> str | None:
		if not location:
			return None
		parsed = urlsplit(location)
		if parsed.scheme:
			path = parsed.path
		else:
			path = location
		if parsed.fragment and not path:
			return None
		virtual = cls.NormalizePath(path)
		return virtual or None

	@staticmethod
	def LocationVariants(location: str) -> set[str]:
		res: set[str] = {location}
		parsed = urlsplit(location)
		if parsed.scheme:
			full = parsed.geturl()
			res.add(full)
			if parsed.path:
				path = parsed.path
				decoded_path = unquote(path)
				segments = [s for s in decoded_path.split("/") if s]
				is_specific_path = len(segments) >= 2 or (
					len(segments) == 1 and "." in segments[0]
				)
				if is_specific_path and not parsed.query:
					res.add(path)
					res.add(decoded_path)
				if parsed.query:
					res.add(f"{path}?{parsed.query}")
				if parsed.fragment:
					res.add(f"{path}#{parsed.fragment}")
		else:
			res.add(unquote(location))
			if location.startswith("/"):
				res.add(location[1:])
			if RE_SCHEME.match(location):
				res.add(location)
		return {k for k in res if k}


def parseMHTML(path: Path) -> MHTMLDocument:
	return MHTMLDocument.Parse(path)


# EOF
