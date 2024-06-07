from typing import (
    Any,
    NamedTuple,
    Iterator,
    Generator,
    Awaitable,
    TypeAlias,
    Union,
    Callable,
    AsyncGenerator,
)
from ..utils.primitives import TPrimitive
import os.path
import inspect
from enum import Enum
from .status import HTTP_STATUS
from ..utils.io import DEFAULT_ENCODING
from .api import ResponseFactory
from pathlib import Path

# NOTE: MyPyC doesn't support async generators. We're trying without.


TControl = bool | None
DEFAULT_ENCODING = "UTF8"


# -----------------------------------------------------------------------------
#
# DATA MODEL
#
# -----------------------------------------------------------------------------


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
    payload: bytes = b""
    length: int = 0
    remaining: int = 0

    @property
    def raw(self) -> bytes:
        return self.payload

    async def load(
        self,
    ) -> bytes | None:
        return self.payload


class HTTPRequestBody:
    def __init__(
        self, instream: Iterator[Awaitable[bytes]], expected: int | None = None
    ):
        self.instream: Iterator[Awaitable[bytes]] = instream
        self.expected: int | None = None

    async def load(
        self,
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


HTTPRequestAtom: TypeAlias = Union[
    HTTPRequestLine,
    HTTPRequestHeaders,
    HTTPRequestBlob,
    HTTPRequestBody,
    HTTPRequestStatus,
    "HTTPRequest",
]


class HTTPResponseBlob(NamedTuple):
    payload: bytes
    length: str


class HTTPResponseFile(NamedTuple):
    path: Path
    fd: int | None = None


class HTTPResponseStream(NamedTuple):
    stream: Generator[str | bytes | TPrimitive, Any, Any]


class HTTPResponseAsyncStream(NamedTuple):
    stream: AsyncGenerator[str | bytes | TPrimitive, Any]


HTTPResponseBody: TypeAlias = (
    HTTPResponseBlob | HTTPResponseFile | HTTPResponseStream | HTTPResponseAsyncStream
)


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
    name = name.lower()
    n: str | None = headers.get(name)
    if n:
        return n
    else:
        n = "-".join(_.capitalize() for _ in name.split("-"))
        headers[name] = n
        return n


# -----------------------------------------------------------------------------
#
# REQUESTS
#
# -----------------------------------------------------------------------------


class HTTPRequest(ResponseFactory["HTTPResponse"]):

    __slots__ = [
        "protocol",
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
        body: HTTPRequestBody | HTTPRequestBlob | None = None,
        protocol: str = "HTTP/1.1",
    ):
        super().__init__()
        self.method: str = method
        self.path: str = path
        self.query: str | None = query
        self.protocol: str = protocol
        self._headers: HTTPRequestHeaders = headers
        self.body: HTTPRequestBody | HTTPRequestBlob | None = body
        self._onClose: Callable[[HTTPRequest], None] | None = None

    @property
    def headers(self) -> dict[str, str]:
        return self._headers.headers

    def getHeader(self, name: str) -> str | None:
        return self._headers.headers.get(name.lower())

    @property
    def contentType(self) -> str | None:
        return self._headers.contentType

    @property
    def contentLength(self) -> int | None:
        return self._headers.contentLength

    def onClose(
        self, callback: Callable[["HTTPRequest"], None] | None
    ) -> "HTTPRequest":
        self._onClose = callback
        return self

    async def load(self, timeout: float | None = None):
        return b""

    def respond(
        self,
        content: Any = None,
        contentType: str | None = None,
        contentLength: int | None = None,
        status: int = 200,
        message: str | None = None,
    ) -> "HTTPResponse":
        return HTTPResponse.Create(
            status=status,
            message=message,
            content=content,
            contentType=contentType,
            protocol=self.protocol,
        )

    # =========================================================================
    # API
    # =========================================================================

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
        if contentType and (not headers or headers.get("content-type") != contentType):
            updated_headers["content-type"] = contentType
        # We process the body
        body: (
            HTTPResponseBlob
            | HTTPResponseFile
            | HTTPResponseStream
            | HTTPResponseAsyncStream
            | None
        ) = None
        content_length: str | None = None
        if content is None:
            pass
        elif isinstance(content, str):
            payload = content.encode(DEFAULT_ENCODING)
        elif isinstance(content, bytes):
            payload = content
        elif isinstance(content, Path):
            body = HTTPResponseFile(content.absolute())
            content_length = str(os.path.getsize(body.path))
        elif inspect.isgenerator(content):
            body = HTTPResponseStream(content)
        elif inspect.isasyncgen(content):
            body = HTTPResponseAsyncStream(content)
        else:
            raise ValueError(f"Unsupported content {type(content)}:{content}")
        # If we have a payload then it's a Blob response
        if payload is not None:
            body = HTTPResponseBlob(payload, str(len(payload)))
            content_length = body.length
        # TODO: We should have a response pipeline that can do things
        # like ETags, Ranged requests, etc.
        # We adjust any extra header
        if content_length and (
            not headers or headers.get("content-length") != content_length
        ):
            updated_headers["content-length"] = content_length
        # --
        # The response is ready to be packaged
        return HTTPResponse(
            status=status,
            message=message or HTTP_STATUS.get(status, "Unknown status"),
            headers=(headers | updated_headers) if headers else updated_headers,
            body=body,
            protocol=protocol,
        )

    __slots__ = ["protocol", "status", "message", "headers", "body"]

    def __init__(
        self,
        protocol: str,
        status: int,
        message: str | None,
        headers: dict[str, str],
        body: HTTPResponseBody | None = None,
    ):
        super().__init__()
        self.protocol: str = protocol
        self.status: int = status
        self.message: str | None = message
        # NOTE: Content-Disposition headers may have a non-ascii value, but we
        # don't support that.
        self.headers: dict[str, str] = headers
        self.body: HTTPResponseBody | None = body

    def getHeader(self, name: str) -> str | None:
        return self.headers.get(name.lower())

    def setHeader(self, name: str, value: str | int | None) -> "HTTPResponse":
        if value is None:
            del self.headers[name.lower()]
        else:
            self.headers[name.lower()] = str(value)
        return self

    def setHeaders(self, headers: dict[str, str | int | None]) -> "HTTPResponse":
        for k, v in headers.items():
            self.setHeader(k, v)
        return self

    def head(self) -> bytes:
        """Serializes the head as a payload."""
        status: int = 204 if self.body is None else self.status
        message: str = self.message or HTTP_STATUS[status]
        lines: list[str] = [f"{headername(k)}: {v}" for k, v in self.headers.items()]
        # TODO: No Content support?
        lines.insert(0, f"{self.protocol} {status} {message}")
        lines.append("")
        lines.append("")
        return "\r\n".join(lines).encode("ascii")

    def __str__(self):
        return f"Response({self.protocol} {self.status} {self.message} {self.headers} {self.body})"


# EOF
