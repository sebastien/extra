# Local files module
from pathlib import Path
from typing import Union, Optional, Callable
from ..decorators import on
from ..model import Service
from ..protocols.http import HTTPRequest
from ..utils.files import contentType
import os


class FileService(Service):
    """A service to serve files from the local filesystem"""

    def __init__(self, root: Optional[Path] = None):
        super().__init__()
        self.root: Path = Path(".") if not root else root
        self.canWrite: Callable[[HTTPRequest, Path], bool] = lambda r, p: False
        self.canRead: Callable[[HTTPRequest, Path], bool] = lambda r, p: True
        self.canDelete: Callable[[HTTPRequest, Path], bool] = lambda r, p: True

    @on(INFO="/{path:any}")
    def info(self, request: HTTPRequest, path: str):
        local_path = self.resolvePath(path)
        if not self.canRead(request, local_path):
            return request.notAuthorized(f"Not authorized to access path: {path}")
        else:
            return request.respond("OK")

    # TODO: Support head
    @on(GET="/{path:any}")
    def read(self, request: HTTPRequest, path: str):
        local_path = self.resolvePath(path)
        if not self.canRead(request, local_path):
            return request.notAuthorized(f"Not authorized to access path: {path}")
        elif not local_path.exists():
            return request.notFound()
        else:
            # TODO: Should support Range requests
            # TODO: Should support ETag/Caching
            # TODO: Should support compression
            # TODO: Should support return a stream reader
            def reader():
                fd: int = os.open(local_path, os.O_RDONLY)
                try:
                    while chunk := os.read(fd, 128_000):
                        yield chunk
                finally:
                    os.close(fd)

            return request.respondStream(reader(), contentType(local_path))

    @on(PUT_PATCH="/{path:any}")
    def write(self, request: HTTPRequest, path: str):
        local_path = self.resolvePath(path)
        if not self.canWrite(request, local_path):
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
        if not self.canWrite(request, local_path):
            return request.notAuthorized(f"Not authorized to delete path: {path}")
        if self.canDelete(request, local_path):
            # NOTE: We don't use self.resolvePath, as we want to bypass resolvers
            if local_path.exists():
                os.unlink(local_path)
                return request.returns(True)
            else:
                return request.returns(False)

    def resolvePath(self, path: Union[str, Path]) -> Path:
        return self.root.joinpath(path)


# EOF
