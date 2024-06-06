from typing import Iterator, NamedTuple, ClassVar, Literal
from enum import Enum


EOL: bytes = b"\r\n"
END: int = 1


class HTTPRequestLine(NamedTuple):
    method: str
    path: str
    params: str
    protocol: str


class HTTPRequestHeaders(NamedTuple):
    headers: dict[str, str]
    contentType: str | None = None
    contentLength: int | None = None


class HTTPRequestBody(NamedTuple):
    data: bytes
    length: int
    remaining: int = 0


class HTTPRequestStatus(Enum):
    Body = 1
    Complete = 2


HTTPRequestAtom = (
    HTTPRequestLine | HTTPRequestHeaders | HTTPRequestBody | HTTPRequestStatus
)


class LineParser:
    __slots__ = ["data", "eol"]

    def __init__(self) -> None:
        self.data: list[bytes] = []
        self.eol: bytes = EOL

    def reset(self, eol: bytes = EOL) -> "LineParser":
        self.data.clear()
        self.eol = eol
        return self

    def flushstr(self) -> str:
        res: str = b"".join(self.data).decode("ascii")
        self.data.clear()
        return res

    def feed(self, chunk: bytes, start: int = 0) -> tuple[list[bytes] | None, int]:
        end = chunk.find(self.eol, start)
        if end == -1:
            self.data.append(chunk[start:] if start else chunk)
            return None, len(chunk) - start
        else:
            self.data.append(chunk[start:end])
            return self.data, (end + 2) - start


class RequestParser:

    __slots__ = ["line", "value"]

    def __init__(self) -> None:
        self.line: LineParser = LineParser()
        self.value: HTTPRequestLine | None = None

    def flush(self) -> "HTTPRequestLine|None":
        res = self.value
        self.value = None
        return res

    def reset(self) -> "RequestParser":
        self.line.reset()
        self.value = None
        return self

    def feed(self, chunk: bytes, start: int = 0) -> tuple[bool | None, int]:
        chunks, end = self.line.feed(chunk, start)
        if chunks:
            # NOTE: This is safe
            l = b"".join(chunks).decode("ascii")
            i = l.find(" ")
            j = l.rfind(" ")
            p: list[str] = l[i + 1 : j].split("?", 1)
            # NOTE: There may be junk before the method name
            self.value = HTTPRequestLine(
                l[0:i], p[0], p[1] if len(p) > 1 else "", l[j + 1 :]
            )
            return True, end
        else:
            return None, end

    def __str__(self) -> str:
        return f"RequestParser({self.value})"


class HeadersParser:

    __slots__ = ["previous", "headers", "contentType", "contentLength", "line"]

    def __init__(self) -> None:
        super().__init__()
        self.line: LineParser = LineParser()
        self.headers: dict[str, str] = {}
        self.contentType: str | None = None
        self.contentLength: int | None = None
        # TODO: Close header
        # self.close:bool = False

    def flush(self) -> "HTTPRequestHeaders|None":
        res = HTTPRequestHeaders(self.headers, self.contentType, self.contentLength)
        self.reset()
        return res

    def reset(self) -> "HeadersParser":
        self.line.reset()
        self.headers = {}
        self.contentType = None
        self.contentLength = None
        return self

    def feed(self, chunk: bytes, start: int = 0) -> tuple[bool | None, int]:
        chunks, end = self.line.feed(chunk, start)
        if chunks is None:
            return None, end
        elif chunks:
            l = self.line.flushstr()
            i = l.find(":")
            if not l:
                return False, end
            elif i != -1:
                # TODO: We should probably normalize the header there
                h = l[:i].lower().strip()
                v = l[i + 1 :].strip()
                if h == "content-length":
                    try:
                        self.contentLength = int(v)
                    except ValueError:
                        self.contentLength = None
                elif h == "content-type":
                    self.contentType = v
                self.headers[h] = v
                return True, end
            else:
                return None, end
        else:
            # An empty line denotes the end of headers
            return False, end

    def __str__(self) -> str:
        return f"HeadersParser({self.headers})"


class BodyEOSParser:

    __slots__ = ["line"]

    def __init__(self) -> None:
        self.line = LineParser()

    def reset(self, eos: bytes = EOL) -> "BodyEOSParser":
        self.line.reset(eos)
        return self

    def feed(self, chunk: bytes, start: int = 0) -> tuple[list[bytes] | None, int]:
        chunks, end = self.line.feed(chunk, start)
        if chunks is None:
            return None, end
        else:
            res = chunks.copy()
            self.line.reset()
            return res, end


class BodyLengthParser:
    """Parses the body of a request with ContentLength set"""

    __slots__ = ["expected", "read", "data"]

    def __init__(self) -> None:
        self.expected: int | None = None
        self.read: int = 0
        self.data: list[bytes] = []

    def flush(self) -> HTTPRequestBody:
        # TODO: We should check it's expected
        res = HTTPRequestBody(
            b"".join(self.data),
            self.read,
            0 if self.expected is None else self.expected - self.read,
        )
        self.reset()
        return res

    def reset(self, length: int | None = None) -> "BodyLengthParser":
        print("RESET BODY", length, self)
        self.expected = length
        self.read = 0
        self.data.clear()
        return self

    def feed(self, chunk: bytes, start: int = 0) -> tuple[bool, int]:
        print("BODY FEED", chunk, "/", self.expected, self.read, "+", start)
        size: int = len(chunk)
        left: int = size - start
        to_read: int = min(
            left, left if self.expected is None else self.expected - self.read
        )
        if to_read < left:
            print("BODY add.a", chunk, start, to_read)
            self.data.append(chunk[start : start + to_read])
            return False, to_read
        else:
            print("BODY add.b", chunk, start)
            self.data.append(chunk[start:] if start else chunk)
            print("===", self.data)
            return True, left


class HTTPParser:
    """A stateful HTTP parser."""

    HAS_BODY: ClassVar[set[str]] = {"POST", "PUT", "PATCH"}

    def __init__(self) -> None:
        self.request: RequestParser = RequestParser()
        self.headers: HeadersParser = HeadersParser()
        self.bodyEOS: BodyEOSParser = BodyEOSParser()
        self.bodyLength: BodyLengthParser = BodyLengthParser()
        self.parser: (
            RequestParser | HeadersParser | BodyEOSParser | BodyLengthParser
        ) = self.request

    def feed(self, chunk: bytes) -> Iterator[HTTPRequestAtom]:
        size: int = len(chunk)
        o: int = 0
        line: HTTPRequestLine | None = None
        headers: HTTPRequestHeaders | None = None
        while o < size:
            print("PARSING AT", o, self.parser)
            l, n = self.parser.feed(chunk, o)
            if l is not None:
                if self.parser is self.request:
                    # We've parsed a request line
                    line = self.request.flush()
                    if line is not None:
                        yield line
                        self.parser = self.headers
                elif self.parser is self.headers:
                    if l is False:
                        # We've parsed the headers
                        headers = self.headers.flush()
                        if headers is not None:
                            yield headers
                        if line and line.method not in self.HAS_BODY:
                            yield HTTPRequestBody(b"", 0)
                        elif headers is not None:
                            match headers.contentLength:
                                case None:
                                    self.parser = self.bodyEOS.reset(b"\n")
                                    yield HTTPRequestStatus.Body
                                case int(n):
                                    self.parser = self.bodyLength.reset(n)
                                    yield HTTPRequestStatus.Body
                elif self.parser is self.bodyEOS:
                    yield self.parser.flush()
                    self.parser = self.headers.reset()
                elif self.parser is self.bodyLength:
                    yield self.parser.flush()
                    self.parser = self.request.reset()
                else:
                    raise RuntimeError(f"Unsupported parser: {self.parser}")
            o += n
            if not n:
                print("Not sure this is good", o)
                raise NotImplementedError


# EOF
