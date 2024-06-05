from typing import Self, Generator


# NOTE: MyPyC doesn't support async generators. We're trying without.

TControl = bool | None


class Request:

    __slots__ = ["method", "path", "params", "headers", "instream"]

    def __init__(self, method: str, path: str, params: str):
        self.method: str = method
        self.path: str = path
        self.params: str = params
        self.headers: dict[str, str] = {}
        self.instream: Generator[bytes, TControl, None] | None = None

    def reset(self, method: str, path: str, params: str) -> Self:
        self.method = method
        self.path = path
        self.params = params
        self.headers.clear()
        return self

    def read(self) -> Generator[bytes, TControl, None]:
        ctrl: TControl = None
        if self.instream:
            while True:
                try:
                    atom = self.instream.send(ctrl)
                except StopIteration:
                    break
                ctrl = yield atom


class Response:
    __slots__ = ["status", "message", "headers", "outstream"]

    def __init__(self, status: int, message: str):
        self.status: int = status
        self.message: str = message
        self.headers: dict[str, str] = {}
        self.outstream: Generator[bytes, TControl, None] | None = None
