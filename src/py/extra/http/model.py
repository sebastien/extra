from typing import Generator, Self, Any, NamedTuple
from .status import HTTP_STATUS
from ..config import DEFAULT_ENCODING

# NOTE: MyPyC doesn't support async generators. We're trying without.

TControl = bool | None
DEFAULT_ENCODING = "UTF8"


class HTTPRequestError(Exception):
    pass


class HTTPRequest:

    __slots__ = ["method", "path", "params", "headers"]

    def __init__(self, method: str, path: str, headers: dict[str, str]):
        self.method: str = method
        print("XXX PATH", path)
        p: list[str] = path.split("?", 1)
        self.path: str = p[0]
        self.params: str = p[1] if len(p) > 1 else ""
        self.headers: dict[str, str] = headers

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

    def respond(
        self,
        content: Any = None,
        contentType: str | None = None,
        status: int = 200,
        message: str | None = None,
    ) -> "HTTPResponse":
        return HTTPResponse.Create(
            status=status,
            message=message,
            content=content,
            contentType=contentType,
        )

    # def respond(
    #     self,
    # ) -> "HTTPResponse":
    #     pass
    def __str__(self):
        return f"Request({self.method} {self.path}{f'?{self.params}' if self.params else ''} {self.headers})"


# We do separate the body, as typically the head of the request is there
# as a whole, and the body can be loaded through different loaders based
# on use case.
class HTTPRequestBody:
    pass


class HTTPResponseBlob(NamedTuple):
    payload: bytes
    length: str


def headername(name: str, *, headers: dict[str, str] = {}) -> str:
    """Normalizes the header name."""
    n: str | None = headers.get(name)
    if n:
        return n
    else:
        n = "-".join(_.capitalize() for _ in name.split("-"))
        headers[name] = n
        return n


class HTTPResponse(NamedTuple):
    status: int
    message: str
    # NOTE: Content-Disposition headers may have a non-ascii value, but we
    # don't support that.
    headers: dict[str, str]
    body: HTTPResponseBlob | None = None
    protocol: str = "HTTP/1.1"

    def head(self) -> bytes:
        """Serializes the head as a payload."""
        lines: list[str] = [f"{headername(k)}: {v}" for k, v in self.headers.items()]
        lines.insert(0, f"{self.protocol} {self.status} {self.message}")
        lines.append("")
        lines.append("")
        return "\r\n".join(lines).encode("ascii")

    @staticmethod
    def Create(
        content: Any = None,
        contentType: str | None = None,
        headers: dict[str, str] | None = None,
        status: int = 200,
        message: str | None = None,
    ) -> "HTTPResponse":
        """Factory method to create HTTP response objects."""
        payload: bytes | None = None
        updated_headers: dict[str, str] = {} if headers is None else {}
        if contentType and updated_headers.get("content-type") != contentType:
            updated_headers = (
                updated_headers.copy()
                if updated_headers is headers
                else updated_headers
            )
            updated_headers["content-type"] = contentType
        if isinstance(content, str):
            payload = content.encode(content, DEFAULT_ENCODING)
        elif isinstance(content, bytes):
            payload = content
        body: HTTPResponseBlob | None = None
        if payload is not None:
            body = (
                HTTPResponseBlob(payload, str(len(payload)))
                if payload is not None
                else None
            )
        if body:
            if updated_headers.get("content-length") != body.length:
                updated_headers = (
                    updated_headers.copy()
                    if updated_headers is headers
                    else updated_headers
                )
                updated_headers["content-length"] = body.length
        return HTTPResponse(
            status=status,
            message=message or HTTP_STATUS.get(status, "Unknown status"),
            headers=updated_headers,
            body=body,
        )


class ResponseAPI:
    def notAuthorized(self):
        pass

    def notFound(self):
        pass

    def notModified(self):
        pass

    def fail(self):
        pass

    def redirect(self):
        pass

    def html(self):
        pass

    def text(self):
        pass

    def json(self):
        pass

    def returns(self):
        pass


# EOF
