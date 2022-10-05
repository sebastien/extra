# Local files module
from pathlib import Path
from typing import Union, Optional
from ..decorators import on
from ..model import Service
from ..protocol.http import HTTPRequest


class FileService(Service):
    def __init__(self, root: Path = "."):
        super().__init__()
        self.root = Path(root)
        self.canWrite = lambda r, p: False
        self.canRead = lambda r, p: True

    @on(INFO="/{path:any}")
    def info(self, request: HTTPRequest, path: str):
        local_path = self.resolvePath(path)
        if not self.canRead(request, local_path):
            return request.notAuthorized(f"Not authoried to access path: {path}")
        return request.respond("OK")

    @on(GET="/{path:any}")
    def read(self, request: HTTPRequest, path: str):
        local_path = self.resolvePath(path)
        if not self.canRead(request, local_path):
            return request.notAuthorized(f"Not authoried to access path: {path}")
        return request.respond("OK")

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
