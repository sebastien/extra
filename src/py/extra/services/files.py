import os
from abc import abstractmethod
from email.utils import formatdate
from hashlib import md5
from html import escape
from pathlib import Path
from typing import Callable, Union

from ..decorators import on
from ..features.cors import cors
from ..http.model import HTTPRequest, HTTPResponse
from ..model import Service
from ..utils.files import FileEntry, contentType, resolveSuffix
from ..utils.htmpl import H, Node, html
from ..utils.shell import shell

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


class FileService(Service):
	"""A service to serve files from the local filesystem"""

	TRANSLATORS: list[FileTranslator] = [TypeScriptTranslator()]

	def __init__(self, root: str | Path | None = None, strict: bool = True):
		super().__init__()
		self.strictLocalPath: bool = strict
		self.root: Path = (
			root if isinstance(root, Path) else Path(root or ".")
		).resolve()
		self.canWrite: Callable[[HTTPRequest, Path], bool] = lambda r, p: False
		self.canRead: Callable[[HTTPRequest, Path], bool] = lambda r, p: True
		self.canDelete: Callable[[HTTPRequest, Path], bool] = lambda r, p: True
		self.automatic: list[str] = [
			".html",
			".htm",
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

	@cors
	@on(HEAD=("/", "/{path:any}"))
	def head(self, request: HTTPRequest, path: str) -> HTTPResponse:
		local_path, redirect_path = self.resolvePath(path)
		if redirect_path:
			return request.redirect(redirect_path)
		elif not (local_path and self.canRead(request, local_path)):
			return request.notAuthorized(f"Not authorized to access path: {path}")
		elif not local_path.exists():
			return request.notFound()
		else:
			if local_path.is_dir():
				# Directory listing HEAD response
				return request.respond("", contentType="text/html")
			else:
				response = self.respondFile(request, local_path)
				response.body = None
				return response

	@cors
	@on(GET=("/", "/{path:any}"))
	def read(self, request: HTTPRequest, path: str = ".") -> HTTPResponse:
		format: str = request.param("format", "html") or "html"
		raw: bool = request.param("raw") is not None
		local_path, redirect_path = self.resolvePath(path)
		if redirect_path:
			return request.redirect(redirect_path)
		elif not (local_path and self.canRead(request, local_path)):
			return request.notAuthorized(f"Not authorized to access path: {path}")
		elif not local_path.exists():
			return request.notFound()
		else:
			return self.renderPath(request, path, local_path, format=format, raw=raw)

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
		local_path = self.root.joinpath(path).resolve(strict=False)
		original_path = local_path
		with_redirect = False
		if not local_path.is_relative_to(self.root):
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
				index_suffixes = [".html", ".htm", ".ts", ".tsx", ".js", ".jsx"]
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
