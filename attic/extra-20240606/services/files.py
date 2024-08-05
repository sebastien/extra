# Local files module
from pathlib import Path
from typing import Union, Optional, Callable
from ..decorators import on
from ..model import Service
from ..protocols.http import HTTPRequest, HTTPResponse
from ..features.cors import cors
from ..utils.htmpl import H, html
import os


FILE_CSS = """
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

    def __init__(self, root: Optional[Path] = None):
        super().__init__()
        self.root: Path = (Path(".") if not root else root).absolute()
        self.canWrite: Callable[[HTTPRequest, Path], bool] = lambda r, p: False
        self.canRead: Callable[[HTTPRequest, Path], bool] = lambda r, p: True
        self.canDelete: Callable[[HTTPRequest, Path], bool] = lambda r, p: True

    def renderPath(self, request: HTTPRequest, path: str, localPath: Path):
        path = path.strip("/")
        if localPath.is_dir():
            return self.renderDir(request, path, localPath)
        else:
            return request.respondFile(localPath)

    def renderDir(
        self, request: HTTPRequest, path: str, localPath: Path
    ) -> HTTPResponse:
        files: list[str] = []
        dirs: list[str] = []
        if localPath.is_dir():
            for p in localPath.iterdir():
                if p.is_dir():
                    dirs.append(H.li(H.a(f"{p.name}/", href=f"/{path}/{p.name}")))
                else:
                    files.append(H.li(H.a(p.name, href=f"/{path}/{p.name}")))
        nodes = []
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
        parent = os.path.dirname(path)
        current = os.path.basename(path)
        return request.respondHTML(
            html(
                H.html(
                    H.head(
                        H.meta(charset="utf-8"),
                        H.title(path),
                        H.style(FILE_CSS),
                        H.body(
                            H.h1(
                                "Listing for ",
                                H.a(f"{parent}/", href=f"/{parent}/") if parent else "",
                                current,
                            ),
                            *nodes,
                            H.div(H.small("Served by Extra")),
                        ),
                    ),
                )
            )
        )

    # @on(GET_HEAD="/favicon.ico")
    # def favicon(self, request: HTTPRequest, path: str):

    @on(INFO=("/", "/{path:any}"))
    def info(self, request: HTTPRequest, path: str):
        local_path = self.resolvePath(path)
        if not (local_path and self.canRead(request, local_path)):
            return request.notAuthorized(f"Not authorized to access path: {path}")
        else:
            return request.respond("OK")

    @cors
    @on(HEAD=("/", "/{path:any}"))
    def head(self, request: HTTPRequest, path: str):
        local_path = self.resolvePath(path)
        if not (local_path and self.canRead(request, local_path)):
            return request.notAuthorized(f"Not authorized to access path: {path}")
        else:
            return request.respond("")

    @cors
    @on(GET=("/", "/{path:any}"))
    def read(self, request: HTTPRequest, path: str = "."):
        local_path = self.resolvePath(path)
        if not (local_path and self.canRead(request, local_path)):
            return request.notAuthorized(f"Not authorized to access path: {path}")
        elif not local_path.exists():
            return request.notFound()
        else:
            return self.renderPath(request, path, local_path)

    @on(PUT_PATCH="/{path:any}")
    def write(self, request: HTTPRequest, path: str = "."):
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
    def delete(self, request, path):
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

    def resolvePath(self, path: Union[str, Path]) -> Optional[Path]:
        path = self.root.joinpath(path).absolute()
        if path.parts[: len(parts := self.root.parts)] == parts:
            return path
        else:
            return None
        return path if path.parts[: len(parts := self.root.parts)] == parts else None


# EOF
