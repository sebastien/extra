from ..utils import Flyweight
from ..protocols import (
    Request,
    Response,
    ResponseStep,
    ResponseBody,
    ResponseBodyType,
    Headers,
    ResponseControl,
    asBytes,
)
from typing import (
    Any,
    Optional,
    Union,
    ClassVar,
    BinaryIO,
    Iterable,
    Iterator,
    cast,
)
from ..utils.files import contentType as guessContentType
from pathlib import Path
from tempfile import SpooledTemporaryFile
from urllib.parse import parse_qs
from asyncio import StreamReader, wait_for
from io import BytesIO
from enum import Enum
import hashlib
import os
import time
import json
import tempfile

# --
# # HTTP Protocol Module
#
# This module is an evolution of Retro's [core
# module](https://github.com/sebastien/retro/blob/main/src/py/retro/core.py),
# that defines the main ways to interact with HTTP data. This reimplementation
# updates the style to leverage type, decorators and have a generally
# simplified and streamlined API.
#
# Here are the principles we're following in the implementation:
#
# - Full typing for `mypyc` compilation
# - As few allocations as possible, we use pre-allocated data as much as we can
# - Streaming support everywhere to support sync and async modes
# - Everything is bytes, so it's ready to be output

# 8Mib spool size
SPOOL_MAX_SIZE = 8 * 1024 * 1024
BUFFER_MAX_SIZE = 1 * 1024 * 1024

Range = tuple[int, int]
ContentType = b"Content-Type"
ContentLength = b"Content-Length"
ContentDisposition = b"Content-Disposition"
ContentDescription = b"Content-Description"
Location = b"Location"

BAD_REQUEST: bytes = b"""\
HTTP/1.1 400 Bad Request\r
Content-Length: 0\r
\r
"""


def asJSON(value):
    return bytes(json.dumps(value), "utf8")


# @property
# def userAgent( self ):
#     pass

# @property
# def range( self ):
#     pass

# @property
# def compression( self ):
#     pass


class HTTPParserStep(Enum):
    Request = 0
    Headers = 1
    Body = 2
    End = 3


class HTTPParser:
    """Parses an HTTP request and headers from a stream through the `feed()`
    method."""

    Pool: ClassVar[list["HTTPParser"]] = []

    @classmethod
    def Get(
        cls, address: str, port: int, stats: Optional[dict[str, float]] = None
    ) -> "HTTPParser":
        if cls.Pool:
            return cls.Pool.pop().init(address=address, port=port, stats=stats)
        else:
            return cls(address=address, port=port, stats=stats)

    @classmethod
    def Dispose(cls, value: "HTTPParser"):
        cls.Pool.append(value)
        return None

    # @tag(low-level)
    @classmethod
    def HeaderOffsets(
        cls, data: bytes, start: int = 0, end: Optional[int] = None
    ) -> Iterable[tuple[Range, Range]]:
        """Parses the headers encoded in the `data` from the given `start` offset to the
        given `end` offset."""
        offset: int = start
        end_offset = len(data) if end is None else len(data) + end if end < 0 else end
        while offset < end_offset:
            next_eol = data.find(b"\r\n", offset)
            # If we don't find an EOL, we're reaching the end of the data
            if next_eol == -1:
                next_eol = end_offset
            # Now we look for the value separator
            next_colon = data.find(b":", offset, end_offset)
            # If we don't find a header, there's nothing we can do
            if next_colon == -1:
                continue
            else:
                header_start = offset
                header_end = next_colon
                value_start = next_colon + 1
                value_end = next_eol
                yield ((header_start, header_end), (value_start, value_end))
            # We update the cursor
            offset = next_eol

    @classmethod
    def Header(
        cls, data: bytes, offset: int = 0, end: Optional[int] = None
    ) -> Iterable[tuple[bytes, bytes]]:
        """A wrapper around `HeaderOffsets` that yields slices of the bytes instead of the
        offsets."""
        for (hs, he), (vs, ve) in HTTPParser.HeaderOffsets(data, offset, end):
            yield (data[hs:he], data[vs:ve])

    @classmethod
    def HeaderValueOffsets(
        cls, data: bytes, start: int = 0, end: Optional[int] = None
    ) -> Iterable[tuple[int, int, int, int]]:
        """Parses a header value and returns an iterator of offsets for name and value
        in the `data`.

        `multipart/mixed; boundary=inner` will
        return `{b"":b"multipart/mixed", b"boundary":b"inner"}`
        """
        end_offset = len(data) if end is None else len(data) + end if end < 0 else end
        result: dict[bytes, bytes] = {}
        offset: int = start
        while offset < end_offset:
            # The next semicolumn is the next separator
            field_end: int = data.find(b";", offset)
            if field_end == -1:
                field_end = end_offset
            value_separator: int = data.find(b"=", offset, field_end)
            if value_separator == -1:
                name_start, name_end = offset, offset
                value_start, value_end = offset, field_end
            else:
                name_start, name_end = offset, value_separator
                value_start, value_end = value_separator + 1, field_end
            # We strip everything -- 32 == space in ASCII
            while name_start < name_end and data[name_start] == 32:
                name_start += 1
            while name_start < name_end and data[name_end] == 32:
                name_end -= 1
            while value_start < value_end and data[value_start] == 32:
                value_start += 1
            while value_start < value_end and data[value_end] == 32:
                value_end -= 1
            yield name_start, name_end, value_start, value_end
            offset = field_end + 1

    @classmethod
    def HeaderValue(
        cls, data: bytes, start: int = 0, end: Optional[int] = None
    ) -> dict[bytes, bytes]:
        return dict(
            (data[ks:ke], data[vs:ve])
            for ks, ke, vs, ve in HTTPParser.HeaderValueOffsets(data, start, end)
        )

    def __init__(
        self, address: str, port: int, stats: Optional[dict[str, float]] = None
    ):
        self.address: str = address
        self.port: int = port
        self.started: float = time.monotonic()
        self.stats: dict[str, float] = stats or {}
        self.method: Optional[str] = None
        self.uri: Optional[str] = None
        self.protocol: Optional[str] = None
        self.headers: dict[str, str] = {}
        self.step: HTTPParserStep = HTTPParserStep.Request
        self.rest: Optional[bytes] = None
        self.status: int = 0
        self._stream: Optional[StreamReader] = None
        self.started = 0.0

    def init(self, address: str, port: int, stats: Optional[dict[str, float]] = None):
        self.address = address
        self.port = port
        self.started = time.monotonic()
        self.stats = stats or {}
        self.method = None
        self.uri = None
        self.protocol = None
        self.headers = {}
        self.step = HTTPParserStep.Request
        self.rest = None
        self.status = 0
        self._stream = None
        self.started = 0.0

    def setInput(self, stream: StreamReader):
        self._stream = stream
        return self

    @property
    def hasReachedBody(self) -> bool:
        return self.step.value >= HTTPParserStep.Body.value

    def feed(self, data: bytes) -> int:
        """Feeds data into the context, returning the number of bytes read."""
        if self.step.value >= HTTPParserStep.Headers.value:
            # If we're past reading the headers (>=2), then it's up
            # to the application to decode.
            return 0
        else:
            t: bytes = self.rest + data if self.rest else data
            o: int = 0
            n: int = len(t)
            i: int = 0
            while (
                (i := t.find(b"\r\n", o)) >= 0
                and self.step.value < HTTPParserStep.Body.value
                and o < n
            ):
                self.step = self._parseLine(self.step, t, o, i)
                o = i + 2
            self.rest = t[o:]
            return o

    def _parseChunk(self, data: bytes, start: int = 0, end: Optional[int] = None):
        """Parses a chunk of the data, which MUST have at least one
        /r/n in there and end with /r/n."""
        # NOTE: In essence, this is pretty close to data[stat:end].split("\r\n")
        # 0 = REQUEST
        # 1 = HEADERS
        # 2 = BODY
        # 3 = DONE
        step = self.step
        o = start
        l = end
        # We'll stop once we've parsed headers or reach the end passed above.
        while step.value < HTTPParserStep.Body.value and (
            o < l if l is not None else True
        ):
            # We find the closest line separators. We're guaranteed to
            # find at least one.
            i = data.find(b"\r\n", o)
            # The chunk must have \r\n at the end
            if i < 0:
                raise ValueError(
                    f"Chunk should end with \\r\\n: {repr(data[start:end])} at {start}"
                )
            # Now we have a line, so we parse it
            step = self._parseLine(step, data, o, o + i)
            # And we increase the offset
            o = i + 2
        # We update the state
        self.step = step
        return o

    def _parseLine(
        self,
        step: HTTPParserStep,
        line: bytes,
        start: int = 0,
        end: Optional[int] = None,
    ) -> HTTPParserStep:
        """Parses a line (without the ending `\r\n`), updating the
        context's {method,uri,protocol,headers,step} accordingly. This
        will stop once two empty lines have been encountered."""
        if start == end or start >= len(line):
            return step
        elif step == HTTPParserStep.Request:
            # That's the REQUEST line
            j = line.find(b" ", start)
            k = line.find(b" ", j + 1) if j >= 0 else -1
            if k < 0:
                raise ValueError(f"Could not parse line: {repr(line)}")
            self.method = line[start:j].decode()
            self.uri = line[j + 1 : k].decode()
            self.protocol = line[k + 1 : end].decode()
            return HTTPParserStep.Headers
        elif not line:
            # That's an EMPTY line, probably the one separating the body
            # from the headers
            return HTTPParserStep.Body
        elif step.value >= HTTPParserStep.Headers.value:
            # That's a HEADER line
            # FIXME: Not sure why we need to reassign here
            j = line.find(b":", start)
            if j < 0:
                raise ValueError(f"Malformed header line: {repr(line)}")
            h = line[start:j].decode().strip()
            j += 1
            if j < len(line) and line[j] == " ":
                j += 1
            v = line[j:end].decode().strip()
            self.headers[h] = v
            return HTTPParserStep.Headers
        else:
            return step

    # TODO: We might want to move that to connection, but right
    # now the HTTP context is a better fix.
    # variant of that.
    async def read(self, size: Optional[int] = None) -> Optional[bytes]:
        """Reads `size` bytes from the context's input stream, using
        whatever data is left from the previous data feeding."""
        assert size != 0
        rest: Optional[bytes] = self.rest
        # This method is a little bit contrived because e need to test
        # for all the cases. Also, this needs to be relatively fast as
        # it's going to be used often.
        print("READING REQUEST", size)
        if rest is None:
            if self._stream:
                if size is None:
                    res = await self._stream.read()
                    print("CHUNK.A", res)
                    return res
                else:
                    # FIXME: Somehow when returning directly there
                    # is an issue when receiving large uploaded files, it
                    # will block forever.
                    res = await self._stream.read(size)
                    print("CHUNK.B", res)
                    return res
            else:
                return b""
        else:
            self.rest = None
            if size is None:
                if self._stream:
                    chunk_a: bytes = await self._stream.read()
                    print("CHUNK.C", chunk_a)
                    return chunk_a if rest is None else rest + chunk_a
                else:
                    return rest
            elif rest and len(rest) > size:
                self.rest = rest[size:]
                return rest[:size]
            elif self._stream:
                chunk_b: bytes = await self._stream.read(
                    size - (0 if rest is None else len(rest))
                )
                print("CHUNK.D", chunk_b)
                return chunk_b if not rest else rest + chunk_b
            else:
                return rest or b""

    def asDict(self) -> dict[str, Any]:
        """Exports a JSONable representation of the context."""
        return {
            "method": self.method,
            "uri": self.uri,
            "protocol": self.protocol,
            "address": self.address,
            "port": self.port,
            "headers": [(k, v) for k, v in self.headers.items()],
            "started": self.started,
        }

    def __repr__(self):
        return f"(HTTPParser method={self.method } uri={self.uri} step={self.step} rest={self.rest})"


# --
# ## HTTP Request
#
# The HTTP request object is designed to work both with our custom
# HTTP parser and with other ways (ASGI).

DAYS: tuple[str, ...] = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MONTHS: tuple[str, ...] = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


class HTTPRequest(Request):
    POOL: ClassVar[list["HTTPRequest"]] = []

    @staticmethod
    def Timestamp(t: time.struct_time) -> str:
        """Convenience function to present a time in HTTP cache format"""
        # NOTE: We have to do it here as we don't want to force the locale
        # FORMAT: If-Modified-Since: Sat, 29 Oct 1994 19:43:31 GMT
        return f"{DAYS[t.tm_wday]}, {t.tm_mday:02d} {MONTHS[t.tm_mon - 1]} {t.tm_year} {t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d} GMT"

    def __init__(self):
        super().__init__()
        # NOTE: We use the same type as the HTTP parser
        self.headers: dict[str, str] = {}
        self.protocol: Optional[str] = None
        self.protocolVersion: Optional[str] = None
        self.method: Optional[str] = None
        self.path: Optional[str] = None
        self.query: Optional[str] = None
        self.ip: Optional[str] = None
        self.port: Optional[int] = None
        self.version: Optional[str] = None
        self._body: Optional[RequestBody] = None
        self._reader: Optional[StreamReader] = None
        self._readCount: int = 0
        self._hasMore: bool = True

    @property
    def isInitialized(self) -> bool:
        return self.method != None and self.path != None

    # @group(Flyweight)

    def init(
        self,
        reader: Optional[StreamReader] = None,
        protocol: Optional[str] = None,
        protocolVersion: Optional[str] = None,
        method: Optional[str] = None,
        path: Optional[str] = None,
        query: Optional[str] = None,
        ip: Optional[str] = None,
        port: Optional[int] = None,
        headers: Optional[dict[str, str]] = None,
    ):
        super().init()
        self._reader = reader
        self.headers = headers if headers else {}
        self.protocol = protocol
        self.protocolVersion = protocolVersion
        self.method = method
        self.path = path
        self.query = query
        self.ip = ip
        self.port = port
        self._readCount = 0
        self._hasMore = True
        self._body = None
        return self

    def reset(self):
        super().reset()
        # NOTE: We don't clear the headers, we'll re-assign on init
        self._body = self._body.reset() if self._body else None
        return self

    # @group(Loading)

    # FIXME: Count should probably not be -1 if we want to stream
    async def read(self, count: int = 65_000) -> Optional[bytes]:
        """Only use read if you want to access the raw data in chunks."""
        if self._hasMore and self._reader:
            data: bytes = await self._reader.read()
            read: int = len(data)
            self._hasMore = read == count
            self._readCount += read
            return data
        else:
            return None

    def feed(self, data: bytes):
        """Feeds some (input) data into that request"""
        return self.body.feed(data)

    # TODO: Should adjust timeout
    async def load(self, timeout: float = 20.0) -> "HTTPRequest":
        """Loads all the data and returns a list of bodies."""
        body = self.body
        if not body.isLoaded:
            while True:
                chunk = await wait_for(self.read(), timeout=timeout)
                if chunk is not None:
                    body.feed(chunk)
                else:
                    break
            body.setLoaded(self.contentType)
        return self

    @property
    def body(self) -> "RequestBody":
        if not self._body:
            body = RequestBody.Create()
            try:
                body.contentLength = int(self.headers.get("Content-Length", ""))
            except ValueError:
                pass
            body.contentType = self.headers.get("Content-Type")
            self._body = body
            return body
        else:
            return self._body

    # @group(Headers)
    @property
    def contentLength(self) -> int:
        return int(self.headers.get(ContentType))

    def setContentLength(self, length: int) -> "HTTPRequest":
        self.headers.set(ContentLength, b"%d" % (length))
        return self

    @property
    def contentType(self) -> bytes:
        return self.headers.get(ContentType)

    def setContentType(self, value: Union[str, bytes]) -> "HTTPRequest":
        self.headers.set(ContentType, asBytes(value))
        return self

    def setHeader(self, name: bytes, value: bytes) -> "HTTPRequest":
        self.headers.set(name, value)
        return self

    def getHeader(self, name: bytes) -> Optional[bytes]:
        return self.headers.get(name)

    # @group(Responses)

    def returns(
        self,
        value: Any,
        contentType: Optional[Union[str, bytes]] = b"application/json",
        status: int = 200,
    ) -> "HTTPResponse":
        # FIXME: This should be a stream writer
        return (
            HTTPResponse.Create()
            .init(status=status)
            .setContent(asJSON(value), contentType)
        )

    def respond(
        self,
        value: Any,
        contentType: Optional[Union[str, bytes]] = None,
        status: int = 200,
    ) -> "HTTPResponse":
        return HTTPResponse.Create().init(status=status).setContent(value, contentType)

    def respondHTML(
        self,
        value: Any,
        status: int = 200,
    ) -> "HTTPResponse":
        return self.respond(
            value=value, status=status, contentType=b"text/html; charset=utf-8"
        )

    def respondText(
        self,
        value: Any,
        status: int = 200,
    ) -> "HTTPResponse":
        return self.respond(
            value=value, status=status, contentType=b"text/plain; charset=utf-8"
        )

    def respondJSON(
        self,
        value: Any,
        status: int = 200,
    ) -> "HTTPResponse":
        return self.respond(value=value, status=status, contentType="application/json")

    def redirect(
        self,
        url: bytes,
        content: Optional[Union[str, bytes]] = None,
        contentType=b"text/plain",
        permanent=True,
    ) -> "HTTPResponse":
        """Responds to this request by a redirection to the following URL"""
        return cast(
            HTTPResponse,
            self.respond(
                content, contentType, status=301 if permanent else 302
            ).setHeader(Location, asBytes(url)),
        )

    def respondFile(
        self,
        path: Path,
        contentType: Optional[str] = None,
        status: int = 200,
        contentLength: bool = True,
        etag: Union[bool, str] = True,
        lastModified: bool = True,
        buffer: int = 1024 * 256,
    ) -> "HTTPResponse":
        if not path.exists():
            return self.notFound(asBytes(f"File not found: {path}"))
        content_type: str = contentType or guessContentType(path)
        # --
        # We start by getting range information in case we want/need to do streaming
        # - <http://benramsey.com/blog/2008/05/206-partial-content-and-range-requests/>
        # - <http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html>
        # - <http://tools.ietf.org/html/rfc2616#section-10.2.7>
        content_range: Optional[str] = self.headers.get("range")
        has_range: bool = bool(content_range)
        range_start: int = 0
        range_end: Optional[int] = None
        headers: Headers = Headers()
        if content_range:
            if len(r := content_range.split("=")) > 1:
                rng = r[1].split("-")
                range_start = int(rng[0] or 0)
                range_end = int(rng[1]) if len(rng) > 1 and rng[1] else None
            else:
                # Range is malformed, so we just skip it
                # TODO: We should maybe throw a warning
                pass
        # --
        # We start by looking at the file, if hasn't changed, we won't bother
        # reading it from the filesystem
        has_changed = True
        last_modified: Optional[time.struct_time] = None

        if has_range or lastModified or etag:
            last_modified = time.gmtime(path.stat().st_mtime)
            headers.set(
                b"Last-Modified", bytes(HTTPRequest.Timestamp(last_modified), "utf8")
            )
            try:
                modified_since = time.strptime(
                    self.headers.get("If-Modified-Since", ""),
                    "%a, %d %b %Y %H:%M:%S GMT",
                )
                if modified_since > last_modified:
                    has_changed = False
            except ValueError:
                pass

        # --
        # If the file has changed or if we request ranges or stream
        # then we'll load it and do the whole she bang
        content_length: Optional[int] = None
        full_length: Optional[int] = None
        etag_sig = None
        # We open the file to get its size and adjust the read length and range end
        # accordingly
        with open(path, "rb") as f:
            f.seek(0, 2)
            full_length = f.tell()
            if not has_range:
                content_length = full_length
            else:
                if range_end is None:
                    range_end = full_length - 1
                    content_length = full_length - range_start
                else:
                    content_length = min(
                        range_end - range_start, full_length - range_start
                    )
        if has_range or etag:
            # We don't use the content-type for ETag as we don't want to
            # have to read the whole file, that would be too slow.
            # NOTE: ETag is indepdent on the range and affect the file is a whole
            etag_data = asBytes(f"{path.absolute()}:{last_modified or ''}")
            headers.set(b"ETag", asBytes(f'"{hashlib.sha256(etag_data).hexdigest()}"'))
        if contentLength is True:
            headers.set(b"Content-Length", asBytes(f"{content_length}"))
        if has_range:
            headers.set(b"Accept-Ranges", b"bytes")
            # headers.append(("Connection",    "Keep-Alive"))
            # headers.append(("Keep-Alive",    "timeout=5, max=100"))
            headers.set(
                b"Content-Range",
                b"bytes %d-%d/%d"
                % (range_start or 0, range_end or full_length, full_length),
            )
        # --
        # We prepare the response
        if (lastModified and not has_changed and not has_range) or (
            etag is True and etag_sig and self.headers.get("If-None-Match") == etag_sig
        ):
            return self.notModified()
        else:

            # This is the generator that will stream the file's content
            def reader(path=path, start=range_start, remaining=content_length):
                fd: int = os.open(path, os.O_RDONLY)
                try:
                    os.lseek(fd, start or 0, os.SEEK_SET)
                    while remaining and (chunk := os.read(fd, min(buffer, remaining))):
                        read = len(chunk)
                        remaining -= read
                        if read:
                            yield chunk
                        else:
                            break
                finally:
                    os.close(fd)

            return (
                HTTPResponse.Create()
                .init(
                    headers=headers,
                    status=206 if has_range else status,
                    # TODO: Support compression
                    # compression=self.compression(),
                )
                .addStream(reader(), content_type)
            )

    def respondStream(
        self, stream: Iterator[bytes], contentType=bytes | str
    ) -> "HTTPResponse":
        return HTTPResponse.Create().init(status=200).addStream(stream, contentType)

    # @group(Errors)

    def notAuthorized(
        self, message: Optional[Union[str, bytes]] = None
    ) -> "HTTPResponse":
        return (
            HTTPResponse.Create()
            .init(status=401)
            .setContent(message or b"Operation not authorized")
        )

    def notFound(self, content: bytes = b"Resource not found") -> "HTTPResponse":
        return HTTPResponse.Create().init(status=404).setContent(content)

    def notModified(self, content: bytes = b"Resource not modified") -> "HTTPResponse":
        """Returns an OK 304"""
        return HTTPResponse.Create().init(status=304).setContent(content)


# FROM: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status
# JSON.stringify(Object.values(document.querySelectorAll("dt")).map(_ => _.innerText))
# and then
# CODE = re.compile(r"(\d+)\s(.+)")
# {int(_.group(1)):_.group(2) for _ in (CODE.match(_) for _ in l) if _}
HTTPStatus: dict[int, bytes] = {
    100: b"Continue",
    101: b"Switching Protocols",
    102: b"Processing (WebDAV)",
    103: b"Early Hints",
    200: b"OK",
    201: b"Created",
    202: b"Accepted",
    203: b"Non-Authoritative Information",
    204: b"No Content",
    205: b"Reset Content",
    206: b"Partial Content",
    207: b"Multi-Status (WebDAV)",
    208: b"Already Reported (WebDAV)",
    226: b"IM Used (HTTP Delta encoding)",
    300: b"Multiple Choices",
    301: b"Moved Permanently",
    302: b"Found",
    303: b"See Other",
    304: b"Not Modified",
    305: b"Use Proxy ",
    306: b"unused",
    307: b"Temporary Redirect",
    308: b"Permanent Redirect",
    400: b"Bad Request",
    401: b"Unauthorized",
    402: b"Payment Required ",
    403: b"Forbidden",
    404: b"Not Found",
    405: b"Method Not Allowed",
    406: b"Not Acceptable",
    407: b"Proxy Authentication Required",
    408: b"Request Timeout",
    409: b"Conflict",
    410: b"Gone",
    411: b"Length Required",
    412: b"Precondition Failed",
    413: b"Payload Too Large",
    414: b"URI Too Long",
    415: b"Unsupported Media Type",
    416: b"Range Not Satisfiable",
    417: b"Expectation Failed",
    418: b"I'm a teapot",
    421: b"Misdirected Request",
    422: b"Unprocessable Entity (WebDAV)",
    423: b"Locked (WebDAV)",
    424: b"Failed Dependency (WebDAV)",
    425: b"Too Early ",
    426: b"Upgrade Required",
    428: b"Precondition Required",
    429: b"Too Many Requests",
    431: b"Request Header Fields Too Large",
    451: b"Unavailable For Legal Reasons",
    500: b"Internal Server Error",
    501: b"Not Implemented",
    502: b"Bad Gateway",
    503: b"Service Unavailable",
    504: b"Gateway Timeout",
    505: b"HTTP Version Not Supported",
    506: b"Variant Also Negotiates",
    507: b"Insufficient Storage (WebDAV)",
    508: b"Loop Detected (WebDAV)",
    510: b"Not Extended",
    511: b"Network Authentication Required",
}


class HTTPResponse(Response):
    POOL: ClassVar[list["HTTPResponse"]] = []

    def __init__(self):
        super().__init__()
        self.status: int = 0
        self.reason: Optional[bytes] = None

    def init(
        self,
        *,
        step: ResponseStep = ResponseStep.Initialized,
        bodies: Optional[list[ResponseBody]] = None,
        headers: Optional[Headers] = None,
        status: int = 0,
        reason: Optional[bytes] = None,
    ) -> "HTTPResponse":
        super().init(step=step, headers=headers, status=status, bodies=bodies)
        self.reason = reason
        return self

    def write(self) -> Iterator[bytes]:
        # FIXME: Is it faster to format? This would be interesting to try out
        # TODO: Should probably limit the number of yields
        reason: bytes = (
            self.reason
            if self.reason
            else HTTPStatus.get(self.status, b"Unknown status")
        )
        first_body: Optional[ResponseBody] = self.bodies[0] if self.bodies else None
        yield b"HTTP/1.1 %d %s\r\n" % (self.status, reason)
        if not (self.headers and self.headers.has(ContentType)) and self.bodies:
            for body in self.bodies:
                if content_type := body.contentType:
                    yield b"Content-Type: %s\r\n" % (content_type)
                    break
        if not (self.headers and self.headers.has(ContentLength)) and self.bodies:
            content_length: int = 0
            has_content_length: bool = True
            for body in self.bodies:
                if body.type == ResponseBodyType.Empty:
                    pass
                elif body.type == ResponseBodyType.Value and isinstance(
                    body.content, bytes
                ):
                    content_length += len(body.content)
                else:
                    has_content_length = False
                    break
            if has_content_length:
                yield b"Content-Length: %d\r\n" % (content_length)
        if self.headers:
            for k, l in self.headers.items():
                # TODO: What about the rest?
                yield b"%s: %s\r\n" % (k, l[0])
        yield b"\r\n"
        current: Optional[ResponseControl] = None
        if self.bodies:
            for body in self.bodies:
                if body.type == ResponseBodyType.Empty:
                    pass
                elif body.type == ResponseBodyType.Value:
                    if not body.content:
                        pass
                    elif not isinstance(body.content, bytes):
                        raise RuntimeError(
                            f"Body content should be bytes, got '{type(body.content)}': {body.content}"
                        )
                    else:
                        yield body.content
                elif body.type == ResponseBodyType.Stream:
                    if not isinstance(body.content, Iterator):
                        raise RuntimeError(
                            f"Body content should be iterator, got '{type(body.content)}': {body.content}"
                        )
                    for chunk in body.content:
                        if isinstance(chunk, str):
                            yield bytes(chunk, "utf-8")
                        else:
                            yield chunk
                else:
                    # TODO: That's the Async Iterator
                    raise NotImplementedError(
                        f"Body type not supported yet: {body.type}"
                    )
                #     current = atom
                # elif current == ResponseControl.Chunk:
                #     assert isinstance(bytes, atom)
                #     yield atom

    def __iter__(self) -> Iterator[bytes]:
        return self.write()


# -----------------------------------------------------------------------------
#
# REQUEST BODY
#
# -----------------------------------------------------------------------------

# @note We need to keep this separate


class RequestBodyType(Enum):
    Undefined: ClassVar[str] = "undefined"
    Raw: ClassVar[str] = "raw"
    MultiPart: ClassVar[str] = "multipart"
    JSON: ClassVar[str] = "json"


class RequestBody(Flyweight):

    POOL: ClassVar[list["RequestBody"]] = []

    def __init__(self, isShort: bool = False):
        self.spool: Optional[Union[BytesIO, tempfile.SpooledTemporaryFile]] = None
        self.isShort = isShort
        self.isLoaded = False
        self.contentType: Optional[str] = None
        self.contentLength: Optional[int] = None
        # self.next:Optional[Body] = None
        self._type: RequestBodyType = RequestBodyType.Undefined
        self._raw: Optional[bytes] = None
        self._value: Any = None
        self._written: int = 0

    @property
    def raw(self) -> Optional[bytes]:
        # We don't need the body to be fully loaded
        if self._raw == None:
            if not self.spool:
                pass
            else:
                # TODO: should check that this indeed reads everything
                self.spool.seek(0)
                self._raw = self.spool.read(self._written)
        return self._raw

    @property
    def value(self) -> Any:
        if not self.isLoaded:
            raise Exception("Body is not loaded, 'await request.load()' required")
        if not self._value:
            self.process()
        return self._value

    def reset(self):
        if isinstance(self.spool, BytesIO):
            pass
        elif isinstance(self.spool, tempfile.SpooledTemporaryFile):
            pass
        self.spool = None
        self.isLoaded = False
        self.contentType = None
        self.contentLength = None
        self._written = 0
        self._raw = None
        self._value = None
        return self

    def setLoaded(self, contentType: bytes, contentLength: Optional[int] = None):
        """Sets the body as loaded. It is then ready to be decoded and its
        value field will become accessible."""
        self.contentType = contentType
        self.contentLength = (
            contentLength if contentLength is not None else self._written
        )
        self.isLoaded = True
        return self

    def feed(self, data: bytes):
        """Feeds data to the body's spool"""
        # We lazily create the spool
        if self.isLoaded:
            raise RuntimeError("Trying to write to a body marked as loaded")
        if not self.spool:
            content_length = self.contentLength
            is_short = content_length and content_length <= BUFFER_MAX_SIZE
            self.spool = (
                BytesIO()
                if is_short
                else tempfile.SpooledTemporaryFile(max_size=SPOOL_MAX_SIZE)
            )
        self._written += len(data)
        # If we're reached the content length, then the body is loaded
        if self.contentLength != None and self._written >= self.contentLength:
            self.isLoaded = True
        self.spool.write(data)
        # We invalidate the cache
        self._raw = None
        self._value = None
        return self

    def process(self):
        if not self.contentType:
            pass
        elif self.contentType.startswith("multipart/form-data"):
            if self.spool:
                self.spool.seek(0)
                for headers, data_file in Decode.Multipart(
                    self.spool, parsed_content[b"boundary"]
                ):
                    print(headers, data_file)
                raise NotImplementedError
            else:
                raise NotImplementedError
        else:
            return None


# -----------------------------------------------------------------------------
#
# DECODE
#
# -----------------------------------------------------------------------------


class Decode:
    """A collection of functions to process form data."""

    # NOTE: We encountered some problems with the `email` module in Python 3.4,
    # which lead to writing these functions.
    # http://stackoverflow.com/questions/4526273/what-does-enctype-multipart-form-data-mean
    @classmethod
    def MultipartChunks(
        cls, stream: BinaryIO, boundary: bytes, bufferSize=1024 * 1024
    ) -> Iterable[tuple[str, Any]]:
        """Iterates on a multipart form data file with the given `boundary`, reading `bufferSize` bytes
        for each iteration. This will yield tuples matching what was parsed, like so:

        - `("b", boundary)` when a boundary is found
        - `("h", headers)`  with an map of `header:value` when headers are encountered (header is stripper lowercased)
        - `("d", data)`     with a bytes array of at maximum `bufferSize` bytes.

        Note that this is a low-level method.
        """
        # multipart/form-data
        # assert "multipart/form-data" in contentType or "multipart/mixed" in contentType, "Expected multipart/form-data or multipart/mixed in content type"
        # The contentType is epxected to be
        # >   Content-Type: multipart/form-data; boundary=<BOUNDARY>\r\n
        boundary_length = len(boundary)
        has_more = True
        # FIXME: We should keep indexes instead of copying all the time, this
        # is a big problem.
        rest = b""
        read_size = bufferSize + boundary_length
        state: Optional[str] = None
        # We want this implementation to be efficient and stream the data, which
        # is especially important when large files (imagine uploading a video)
        # are processed.
        while has_more:
            # Here we read bufferSize + boundary_length, and will return at
            # maximum bufferSize bytes per iteration. This ensure that if
            # the read stop somewhere within a boundary we'll stil be able
            # to find it at the next iteration.
            chunk = stream.read(read_size)
            chunk_read_size = len(chunk)
            chunk = rest + chunk
            # If state=="b" it means we've found a boundary at the previous iteration
            # and we need to find the headers
            if state == "b":
                i = chunk.find(b"\r\n\r\n")
                if i >= 0:
                    # FIXME: Should really yield offsets
                    raw_headers: bytes = chunk[:i]
                    yield ("h", raw_headers)
                    chunk = chunk[i + 4 :]
                else:
                    yield ("h", None)
            # Now we look for the next boundary
            i = chunk.find(boundary)
            if i == -1:
                yield ("d", chunk[0:bufferSize])
                rest = chunk[bufferSize:]
                state = "d"
            else:
                # The body will end with \r\n + boundary
                if i > 2:
                    yield ("d", chunk[0 : i - 2])
                rest = chunk[i + boundary_length :]
                yield ("b", boundary)
                state = "b"
            has_more = len(chunk) > 0 or len(chunk) == read_size

    @classmethod
    def Multipart(
        cls, stream: BinaryIO, boundary: bytes, bufferSize=64_000
    ) -> Iterable[tuple[Optional[Headers], Union[SpooledTemporaryFile, bytes]]]:
        """Decodes the given multipart data, yielding `(meta, data)`
        couples, where meta is a parsed dict of headers and data
        is a file-like object."""
        is_new = False
        spool: Optional[SpooledTemporaryFile] = None
        headers: Optional[Headers] = None
        for state, data in Decode.MultipartChunks(stream, boundary):
            if state == "b":
                # We encounter the boundary at the very beginning, or
                # inbetween elements. If we don't have a daa
                if spool:
                    # There might be 2 bytes of data, which will result in
                    # meta being None
                    # TODO: Not sure when/why this happens, should have
                    # a test case.
                    if headers is None:
                        spool.close()
                    else:
                        spool.seek(0)
                        yield (headers, spool)
                is_new = True
                spool = None
                headers = None
            elif state == "h":
                # The header comes next
                assert is_new
                is_new = False
                if data:
                    print("HEADERS", data)
                    headers = Headers.FromItems(data.items())
                else:
                    headers = None
            elif state == "d":
                assert not is_new
                if not spool:
                    spool = tempfile.SpooledTemporaryFile(max_size=SPOOL_MAX_SIZE)
                spool.write(data)
            else:
                raise Exception("State not recognized: {0}".format(state))
        if spool:
            spool.seek(0)
            yield (headers, spool)

    # @classmethod
    # def Multipart( self, stream:BinaryIO, boundary:bytes ):
    #     # We're using the FormData
    #     # FIXME: This assumes headers are Camel-Case
    #     for meta, data in FormData.DecodeMultipart(dataFile, boundary):
    #         # There is sometimes leading and trailing data (not sure
    #         # exaclty why, but try the UploadModule example) to see
    #         # with sample payloads.
    #         if meta is None:
    #             continue
    #         disposition = meta["Content-Disposition"]
    #         # We expect to have a least one of these
    #         name = disposition.get("name") or disposition.get("filename") or meta["Content-Description"]
    #         if name[0] == name[-1] and name[0] in "\"'":
    #             name = name[1:-1]
    #         if "filename" in disposition:
    #             # NOTE: This stores the whole data in memory, we don't want
    #             # that.
    #             new_file= File(
    #                 # FIXME: Shouldnot use read here
    #                 data        = data.read(),
    #                 contentType = meta["Content-Type"][""],
    #                 name        = name,
    #                 filename    = disposition.get("filename") or meta["Content-Description"]
    #             )
    #             self.request._addFile (name, new_file)
    #             self.request._addParam(name, new_file)
    #         else:
    #             self.request._addParam(name, name)

    # NOTE: That's "application/x-www-form-urlencoded"
    @classmethod
    async def FormEncoded(
        self, stream: BinaryIO, charset: Optional[bytes] = None
    ) -> dict[str, list[str]]:
        return parse_qs(stream.read().decode("utf8"))


# EOF
