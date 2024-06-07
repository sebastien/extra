from typing import Generator, Self, Any, NamedTuple, Iterator, Awaitable
from enum import Enum
from abc import ABC
from .status import HTTP_STATUS
from ..config import DEFAULT_ENCODING

# NOTE: MyPyC doesn't support async generators. We're trying without.

TControl = bool | None
DEFAULT_ENCODING = "UTF8"


class HTTPRequestError(Exception):
    pass


class HTTPRequestLine(NamedTuple):
    method: str
    path: str
    query: str
    protocol: str


class HTTPRequestHeaders(NamedTuple):
    headers: dict[str, str]
    contentType: str | None = None
    contentLength: int | None = None


class HTTPRequestBlob(NamedTuple):
    payload: bytes
    length: int
    remaining: int = 0

    @property
    def raw(self) -> bytes:
        return self.payload


class HTTPRequestBody:
    def __init__(
        self, instream: Iterator[Awaitable[bytes]], expected: int | None = None
    ):
        self.instream: Iterator[Awaitable[bytes]] = instream
        self.expected: int | None = None

    async def load(
        self,
        timeout: float = 5.0,
    ) -> bytes | None:
        """Loads all the data and returns a list of bodies."""
        data = bytearray()
        try:
            while True:
                chunk = await next(self.instream)
                data += chunk
        except StopIteration:
            return data


class HTTPRequestStatus(Enum):
    Processing = 0
    Body = 1
    Complete = 2
    Timeout = 10
    NoData = 11
    BadFormat = 12


HTTPRequestAtom = (
    HTTPRequestLine
    | HTTPRequestHeaders
    | HTTPRequestBlob
    | HTTPRequestBody
    | HTTPRequestStatus
)


class HTTPResponseBlob(NamedTuple):
    payload: bytes
    length: str


class HTTPResponseFile(NamedTuple):
    path: str
    fd: int | None = None


class HTTPResponseStream(NamedTuple):
    stream: Iterator[bytes]


class HTTPResponseAsyncStream(NamedTuple):
    stream: Iterator[Awaitable[bytes]]


# We do separate the body, as typically the head of the request is there
# as a whole, and the body can be loaded through different loaders based
# on use case.

# -----------------------------------------------------------------------------
#
# HELPERS
#
# -----------------------------------------------------------------------------


def headername(name: str, *, headers: dict[str, str] = {}) -> str:
    """Normalizes the header name."""
    n: str | None = headers.get(name)
    if n:
        return n
    else:
        n = "-".join(_.capitalize() for _ in name.split("-"))
        headers[name] = n
        return n


# -----------------------------------------------------------------------------
#
# API
#
# -----------------------------------------------------------------------------

# --
# == HTTP Request Response API
#
# Defines the high level API functions (orthogonal to the underlying model)
# to manipulate requests/responses.


class ResponseAPI(ABC):
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


# -----------------------------------------------------------------------------
#
# REQUESTS
#
# -----------------------------------------------------------------------------


class HTTPRequest:

    __slots__ = [
        "method",
        "path",
        "query",
        "_headers",
        "body",
    ]

    def __init__(
        self,
        method: str,
        path: str,
        query: str | None,
        headers: HTTPRequestHeaders,
        body: HTTPRequestBody | None = None,
    ):
        super().__init__()
        self.method: str = method
        self.path: str = path
        self.query: str | None = query
        self._headers: HTTPRequestHeaders = headers
        self.body: HTTPRequestBody | None = body

    @property
    def headers(self) -> dict[str, str]:
        return self._headers.headers

    @property
    def contentType(self) -> str | None:
        return self._headers.contentType

    @property
    def contentLength(self) -> int | None:
        return self._headers.contentLength

    async def load(self, timeout: float | None = None):
        print("LOAD", self.body)
        return b""

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
        return f"Request({self.method} {self.path}{f'?{self.query}' if self.query else ''} {self.headers})"


# -----------------------------------------------------------------------------
#
# RESPONSE
#
# -----------------------------------------------------------------------------


class HTTPResponse:

    @staticmethod
    def Create(
        content: Any = None,
        contentType: str | None = None,
        headers: dict[str, str] | None = None,
        status: int = 200,
        message: str | None = None,
        protocol: str = "HTTP/1.1",
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
            protocol=protocol,
        )

    __slots__ = ["protocol", "status", "message", "headers", "body"]

    def __init__(
        self,
        protocol: str,
        status: int,
        message: str,
        headers: dict[str, str],
        body: HTTPResponseBlob | None = None,
    ):
        super().__init__()
        self.protocol: str = protocol
        self.status: int = status
        self.message: str = message
        # NOTE: Content-Disposition headers may have a non-ascii value, but we
        # don't support that.
        self.headers: dict[str, str] = headers
        self.body: HTTPResponseBlob | None = body

    def head(self) -> bytes:
        """Serializes the head as a payload."""
        lines: list[str] = [f"{headername(k)}: {v}" for k, v in self.headers.items()]
        lines.insert(0, f"{self.protocol} {self.status} {self.message}")
        lines.append("")
        lines.append("")
        return "\r\n".join(lines).encode("ascii")


# EOF
