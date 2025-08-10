from pathlib import Path
from typing import Union, Callable
from ..decorators import on
from ..model import Service
from ..http.model import HTTPRequest, HTTPResponse
from ..features.cors import cors
from ..utils.htmpl import Node, H, html
from ..utils.files import FileEntry
from html import escape
import os


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


class FileService(Service):
	"""A service to serve files from the local filesystem"""

	def __init__(self, root: str | Path | None = None):
		super().__init__()
		self.root: Path = (
			root if isinstance(root, Path) else Path(root or ".")
		).absolute()
		self.canWrite: Callable[[HTTPRequest, Path], bool] = lambda r, p: False
		self.canRead: Callable[[HTTPRequest, Path], bool] = lambda r, p: True
		self.canDelete: Callable[[HTTPRequest, Path], bool] = lambda r, p: True

	def renderPath(
		self,
		request: HTTPRequest,
		path: str,
		localPath: Path,
		format: str,
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
			return request.respondFile(
				localPath, contentType=self.guessContentType(localPath)
			)

	def guessContentType(self, path: Path) -> str | None:
		if path.name == "importmap.json":
			return "application/importmap+json"
		else:
			return None

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
		local_path = self.resolvePath(path)
		if not (local_path and self.canRead(request, local_path)):
			return request.notAuthorized(f"Not authorized to access path: {path}")
		else:
			return request.respond("OK")

	@cors
	@on(HEAD=("/", "/{path:any}"))
	def head(self, request: HTTPRequest, path: str) -> HTTPResponse:
		local_path = self.resolvePath(path)
		if not (local_path and self.canRead(request, local_path)):
			return request.notAuthorized(f"Not authorized to access path: {path}")
		else:
			# FIXME: This should include the headers, type, etc, and it does not
			return request.respond("")

	@cors
	@on(GET=("/", "/{path:any}"))
	def read(self, request: HTTPRequest, path: str = ".") -> HTTPResponse:
		format: str = request.param("format", "html") or "html"
		local_path = self.resolvePath(path)
		if not (local_path and self.canRead(request, local_path)):
			return request.notAuthorized(f"Not authorized to access path: {path}")
		elif not local_path.exists():
			return request.notFound()
		else:
			return self.renderPath(request, path, local_path, format=format)

	@on(PUT_PATCH="/{path:any}")
	def write(self, request: HTTPRequest, path: str = ".") -> HTTPResponse:
		local_path = self.resolvePath(path)
		if not (local_path and self.canWrite(request, local_path)):
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
		local_path = self.resolvePath(path)
		if not (local_path and self.canWrite(request, local_path)):
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

	def resolvePath(self, path: Union[str, Path]) -> Path | None:
		has_slash = isinstance(path, str) and path.endswith("/")
		local_path = self.root.joinpath(path).absolute()
		if not local_path.parts[: len(parts := self.root.parts)] == parts:
			return None
		if local_path.is_dir():
			index_path = local_path / "index.html"
			if not has_slash and index_path.exists():
				return index_path
			else:
				return local_path
		else:
			if not local_path.exists() and not local_path.suffix:
				for suffix in [".html", ".htm", ".txt", ".md"]:
					html_path = local_path.with_suffix(suffix)
					if html_path.exists():
						return html_path
			return local_path


# EOF
