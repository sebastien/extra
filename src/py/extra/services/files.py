import os
import shutil
from abc import abstractmethod
from email.utils import formatdate
from hashlib import md5
from html import escape
from pathlib import Path
from typing import Callable, Union

from ..decorators import on
from ..features.cors import setCORSHeaders
from ..http.model import HTTPRequest, HTTPResponse
from ..model import Service
from ..utils.files import FileEntry, contentType, resolveSuffix
from ..utils.htmpl import H, Node, html, raw
from ..utils.shell import shell
from ..utils.ssi import processSSI

try:
	import paml.engine as _paml_engine  # type: ignore[import-untyped]
except ImportError:
	_paml_engine = None

try:
	import pcss as _pcss  # type: ignore[import-untyped]
except ImportError:
	_pcss = None

FILE_CSS: str = """
:root {
    font-family: sans-serif;
    font-size: 14px;
    line-height: 1.35em;
    padding: 20px;
    background: #F0F0F0;
}
h1 {
margin-top: 1.75em;
margin-bottom: 1.75em;
line-height:1.25em;
}

h2 {
margin-top: 1.25em;
}

ul {
    padding: 0px 20px;
    margin: 1.25em 0em;
}

li {
    padding: 0px 10px;
    margin: 0.5em 0em;
}
"""


# TODO: Support caching
class FileTranslator:
	@abstractmethod
	def match(self, base: Path, path: str, local: Path) -> Path | None: ...

	@abstractmethod
	def translate(self, path: Path) -> tuple[str, bytes | str]: ...


class TypeScriptTranslator(FileTranslator):
	"""Transpiles TypeScript using bun."""

	def match(self, base: Path, path: str, local: Path) -> Path | None:
		# TODO: Should check if Bun is there
		return local if local.suffix in (".ts", ".tsx", ".jsx") else None

	def translate(self, path: Path) -> tuple[str, bytes | str]:
		# TODO: This is fully blocking, we should support streaming or
		# async instead.
		return (
			"text/javascript",
			shell(["bun", "build", "--external", "*", str(path.absolute())]),
		)


class PAMLTranslator(FileTranslator):
	"""Transforms PAML files to HTML, XML or JavaScript."""

	def match(self, base: Path, path: str, local: Path) -> Path | None:
		if _paml_engine is None:
			return None
		name = local.name
		return (
			local
			if name.endswith(".paml")
			or name.endswith(".paml.xml")
			or name.endswith(".paml.js")
			else None
		)

	def translate(self, path: Path) -> tuple[str, bytes | str]:
		name = path.name
		if name.endswith(".paml.xml"):
			fmt, ctype = "xml", "application/xml"
		elif name.endswith(".paml.js"):
			fmt, ctype = "js", "text/javascript"
		else:
			fmt, ctype = "html", "text/html"
		source = path.read_text(encoding="utf8")
		return ctype, _paml_engine.parse(source, path=str(path), format=fmt)


class PCSSTranslator(FileTranslator):
	"""Transforms PCSS files to CSS."""

	def match(self, base: Path, path: str, local: Path) -> Path | None:
		if _pcss is None:
			return None
		return local if local.suffix == ".pcss" else None

	def translate(self, path: Path) -> tuple[str, bytes | str]:
		source = path.read_text(encoding="utf8")
		return "text/css", _pcss.process(source, path=str(path))


class MarkdownTranslator(FileTranslator):
	"""Transforms Markdown files to HTML using pandoc."""

	GITHUB_MARKDOWN_CSS = "https://cdnjs.cloudflare.com/ajax/libs/github-markdown-css/5.8.1/github-markdown.min.css"

	def match(self, base: Path, path: str, local: Path) -> Path | None:
		return local if local.suffix == ".md" and shutil.which("pandoc") else None

	def translate(self, path: Path) -> tuple[str, bytes | str]:
		html_body = shell(
			["pandoc", "--from", "gfm", "--to", "html5"],
			input=path.read_bytes(),
		).decode("utf8")
		document = "".join(
			html(
				H.html(
					H.head(
						H.meta(charset="utf-8"),
						H.meta(name="viewport", content="width=device-width, initial-scale=1.0"),
						H.title(path.name),
						H.link(rel="stylesheet", href=self.GITHUB_MARKDOWN_CSS),
						H.style(
							"body { margin: 0; background: #ffffff; }"
							" .markdown-body { box-sizing: border-box; max-width: 980px; margin: 0 auto; padding: 32px 24px; }"
							" @media (max-width: 767px) { .markdown-body { padding: 16px; } }"
						),
					),
					H.body(H.article(raw(html_body), _="markdown-body")),
				),
				doctype="html",
			)
		)
		return "text/html", document


class SSITranslator(FileTranslator):
	"""Transforms SHTML files by expanding SSI include directives."""

	def __init__(self) -> None:
		self.base: Path | None = None

	def match(self, base: Path, path: str, local: Path) -> Path | None:
		self.base = base
		return local if local.suffix in (".shtml", ".shtm") else None

	def translate(self, path: Path) -> tuple[str, bytes | str]:
		source = path.read_text(encoding="utf8")
		root = self.base or path.parent
		return "text/html", processSSI(source, root=root, current=path)


class FileService(Service):
	"""A service to serve files from the local filesystem"""

	TRANSLATORS: list[FileTranslator] = [
		TypeScriptTranslator(),
		PAMLTranslator(),
		PCSSTranslator(),
		MarkdownTranslator(),
		SSITranslator(),
	]

	def __init__(
		self,
		root: str | Path | None = None,
		strict: bool = True,
		followSymlinks: bool = True,
		enableCORS: bool = True,
		enableSSI: bool = True,
	):
		super().__init__()
		self.strictLocalPath: bool = strict
		self.followSymlinks: bool = followSymlinks
		self.enableCORS: bool = enableCORS
		self.enableSSI: bool = enableSSI
		self.root: Path = (
			root if isinstance(root, Path) else Path(root or ".")
		).resolve()
		self.canWrite: Callable[[HTTPRequest, Path], bool] = lambda r, p: False
		self.canRead: Callable[[HTTPRequest, Path], bool] = lambda r, p: True
		self.canDelete: Callable[[HTTPRequest, Path], bool] = lambda r, p: True
		self.automatic: list[str] = [
			".html",
			".htm",
			".shtml",
			".shtm",
			".pcss",
			".paml",
			".paml.xml",
			".paml.js",
			".txt",
			".md",
			".ts",
			".tsx",
			".js",
			".jsx",
		]

	def renderPath(
		self,
		request: HTTPRequest,
		path: str,
		localPath: Path,
		format: str,
		raw: bool = False,
	) -> HTTPResponse:
		path = path.strip("/")
		if localPath.is_dir():
			match format:
				# We support the JSON format to list the contents of a diretory
				case "json":
					return request.returns(
						[FileEntry.FromPath(_) for _ in localPath.iterdir()]
					)
				case _:
					return self.renderDir(request, path, localPath)
		else:
			# Bypass translators if ?raw is requested
			if not raw:
				for t in self.TRANSLATORS:
					if isinstance(t, SSITranslator) and not self.enableSSI:
						continue
					p = t.match(self.root, path, localPath)
					if p:
						c, b = t.translate(p)
						return request.respond(b, contentType=c)
			return self.respondFile(request, localPath)

	def respondFile(self, request: HTTPRequest, path: Path) -> HTTPResponse:
		return request.respondFile(
			path,
			contentType=self.guessContentType(path),
			acceptEncoding=request.header("Accept-Encoding"),
			ifNoneMatch=request.header("If-None-Match"),
			ifModifiedSince=request.header("If-Modified-Since"),
			ifRange=request.header("If-Range"),
			rangeHeader=request.header("Range"),
		)

	def guessContentType(self, path: Path) -> str | None:
		if path.name == "importmap.json":
			return "application/importmap+json"
		else:
			return contentType(path)

	def getFileHeaders(self, path: Path) -> dict[str, str]:
		"""Generate Last-Modified and ETag headers for a file."""
		headers = {}
		if path.exists():
			stat_info = path.stat()
			# Last-Modified header (RFC 7234)
			headers["Last-Modified"] = formatdate(stat_info.st_mtime, usegmt=True)
			# ETag header using file size and modification time
			etag = md5(
				f"{stat_info.st_size}-{stat_info.st_mtime}".encode(),
				usedforsecurity=False,
			).hexdigest()  # nosec
			headers["ETag"] = f'"{etag}"'
		return headers

	def renderDir(
		self, request: HTTPRequest, path: str, localPath: Path
	) -> HTTPResponse:
		current = os.path.basename(path) or "/"
		parent: str | None = os.path.dirname(path)
		if path == parent:
			parent = None
		if path.endswith("/"):
			path = path[:-1]

		files: list[Node] = []
		dirs: list[Node] = []
		if localPath.is_dir():
			for p in sorted(localPath.iterdir()):
				# We really want the href to be absolute
				href = os.path.join("/", self.PREFIX or "/", path, p.name)
				if p.is_dir():
					dirs.append(H.li(H.a(f"{escape(p.name)}/", href=href)))
				else:
					files.append(H.li(H.a(p.name, href=href)))
		nodes: list[Node] = []

		if parent is not None:
			dirs.insert(0, H.li(H.a("..", href=f"/{parent}")))

		if dirs:
			nodes += [
				H.section(
					H.h2("Directories"),
					H.ul(*dirs, style='list-style-type: "\\1F4C1";'),
				)
			]
		if files:
			nodes += [
				H.section(
					H.h2("Files"), H.ul(*files, style='list-style-type: "\\1F4C4";')
				)
			]
		path_chunks: list[str] = path.split("/")
		prefix = self.PREFIX or "/"
		if not prefix.startswith("/"):
			prefix = f"/{prefix}"
		breadcrumbs: list[Node | str] = [H.a("/", href=prefix)]
		for i, bp in enumerate(path_chunks[:-1]):
			breadcrumbs.append(
				H.a(bp, href=os.path.join(prefix, *path_chunks[: i + 1]))
			)
			breadcrumbs.append("/")
		return request.respondHTML(
			"".join(
				html(
					H.html(
						H.head(
							H.meta(charset="utf-8"),
							H.meta(
								name="viewport",
								content="width=device-width, initial-scale=1.0",
							),
							H.title(path),
							H.style(FILE_CSS),
							H.body(
								H.h1(
									"Listing for ",
									(
										H.a(f"{parent}/", href=f"/{parent}/")
										if parent
										else ""
									),
									current,
								),
								*nodes,
							),
						),
					),
					doctype="html",
				)
			)
		)

	# @on(GET_HEAD="/favicon.ico")
	# def favicon(self, request: HTTPRequest, path: str):

	@on(INFO=("/", "/{path:any}"))
	def info(self, request: HTTPRequest, path: str) -> HTTPResponse:
		local_path, redirect_path = self.resolvePath(path)
		if redirect_path:
			return request.redirect(redirect_path)
		elif not (local_path and self.canRead(request, local_path)):
			return request.notAuthorized(f"Not authorized to access path: {path}")
		else:
			return request.respond("OK")

	@on(HEAD=("/", "/{path:any}"))
	def head(self, request: HTTPRequest, path: str) -> HTTPResponse:
		response: HTTPResponse
		local_path, redirect_path = self.resolvePath(path)
		if redirect_path:
			response = request.redirect(redirect_path)
		elif not (local_path and self.canRead(request, local_path)):
			response = request.notAuthorized(f"Not authorized to access path: {path}")
		elif not local_path.exists():
			response = request.notFound()
		else:
			if local_path.is_dir():
				# Directory listing HEAD response
				response = request.respond("", contentType="text/html")
			else:
				response = self.respondFile(request, local_path)
				response.body = None
		return (
			setCORSHeaders(response, origin=request.getHeader("Origin"))
			if self.enableCORS
			else response
		)

	@on(GET=("/", "/{path:any}"))
	def read(self, request: HTTPRequest, path: str = ".") -> HTTPResponse:
		format: str = request.param("format", "html") or "html"
		raw: bool = request.param("raw") is not None
		response: HTTPResponse
		local_path, redirect_path = self.resolvePath(path)
		if redirect_path:
			response = request.redirect(redirect_path)
		elif not (local_path and self.canRead(request, local_path)):
			response = request.notAuthorized(f"Not authorized to access path: {path}")
		elif not local_path.exists():
			response = request.notFound()
		else:
			response = self.renderPath(request, path, local_path, format=format, raw=raw)
		return (
			setCORSHeaders(response, origin=request.getHeader("Origin"))
			if self.enableCORS
			else response
		)

	@on(PUT_PATCH="/{path:any}")
	def write(self, request: HTTPRequest, path: str = ".") -> HTTPResponse:
		local_path, redirect_path = self.resolvePath(path)
		if redirect_path:
			return request.redirect(redirect_path)
		elif not (local_path and self.canWrite(request, local_path)):
			return request.notAuthorized(f"Not authoried to write to path: {path}")
			# NOTE: We don't use self.resolvePath, as we want to bypass resolvers
			# dirname = os.path.dirname(local_path)
			# if not os.path.exists(dirname): os.makedirs(dirname)
			# request.load()
			# data = request.data()
			# self.app.save(local_path, ensureBytes(data))
			# USE fsync
		return request.returns(True)

	@on(DELETE="/{path:any}")
	def delete(self, request: HTTPRequest, path: str) -> HTTPResponse:
		local_path, redirect_path = self.resolvePath(path)
		if redirect_path:
			return request.redirect(redirect_path)
		elif not (local_path and self.canWrite(request, local_path)):
			return request.notAuthorized(f"Not authorized to delete path: {path}")
		elif self.canDelete(request, local_path):
			# NOTE: We don't use self.resolvePath, as we want to bypass resolvers
			if local_path.exists():
				os.unlink(local_path)
				return request.returns(True)
			else:
				return request.returns(False)
		else:
			return request.returns(False)

	def resolvePath(self, path: Union[str, Path]) -> tuple[Path | None, str | None]:
		has_slash = isinstance(path, str) and path.endswith("/")
		local_path = Path(os.path.abspath(self.root.joinpath(path)))
		original_path = local_path
		with_redirect = False
		if not local_path.is_relative_to(self.root):
			return None, None
		if not self.followSymlinks and not local_path.resolve(
			strict=False
		).is_relative_to(self.root):
			return None, None

		# First try to resolve with automatic extensions (unless path ends with "/")
		if not has_slash and (local_path.is_dir() or not local_path.exists()):
			for suffix in self.automatic:
				translated_path = local_path.parent / f"{local_path.name}{suffix}"
				if translated_path.exists():
					local_path = translated_path
					break

		# Then check if it's a directory
		if local_path.is_dir():
			if not has_slash:
				# NOTE: Maybe this should be handled previously?
				index_suffixes = [
					".html",
					".htm",
					".shtml",
					".shtm",
					".pcss",
					".paml",
					".paml.xml",
					".paml.js",
					".ts",
					".tsx",
					".js",
					".jsx",
				]
				if match := resolveSuffix(local_path / "index", index_suffixes):
					local_path, _ = match
					with_redirect = True

		# Finally return the original path if it exists, or None if it doesn't
		if not local_path.exists():
			return None, None
		elif local_path != original_path:
			redirect_url = (
				"/"
				+ local_path.relative_to(self.root).as_posix()
				+ ("/" if local_path.is_dir() else "")
			)
			return local_path, redirect_url if with_redirect else None
		else:
			return local_path, None


# EOF
