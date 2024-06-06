from typing import Iterator, NamedTuple, ClassVar
from enum import Enum


EOL: bytes = b"\r\n"


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

    __slots__ = ["line", "method", "path", "protocol"]

    def __init__(self) -> None:
        self.line: LineParser = LineParser()
        self.method: str = ""
        self.path: str = ""
        self.protocol: str = ""

    def reset(self) -> "RequestParser":
        self.line.reset()
        self.method = ""
        self.path = ""
        self.protocol = ""
        return self

    def feed(self, chunk: bytes, start: int = 0) -> tuple[bool | None, int]:
        chunks, end = self.line.feed(chunk, start)
        if chunks:
            # NOTE: This is safe
            l = b"".join(chunks).decode("ascii")
            i = l.find(" ")
            j = l.rfind(" ")
            # NOTE: There may be junk before the method name
            self.method = l[0:i]
            self.path = l[i + 1 : j]
            self.protocol = l[j + 1 :]
            return True, end
        else:
            return None, end

    def __str__(self) -> str:
        return f"RequestParser({self.method} {self.path} {self.protocol})"


class HeadersParser:

    __slots__ = ["previous", "headers", "contentType", "contentLength", "line"]

    def __init__(self) -> None:
        super().__init__()
        self.headers: dict[str, str] = {}
        self.line: LineParser = LineParser()
        self.contentType: str | None = None
        self.contentLength: int | None = None
        # TODO: Close header
        # self.close:bool = False

    def flush(self) -> dict[str, str]:
        res = self.headers
        self.headers = {}
        return res

    def reset(self) -> "HeadersParser":
        self.line.reset()
        self.headers.clear()
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
        self.expected: int = 0
        self.read: int = 0
        self.data: list[bytes] = []

    def reset(self, length: int) -> "BodyLengthParser":
        self.expected = length
        self.read = 0
        self.data.clear()
        return self

    def feed(self, chunk: bytes, start: int = 0) -> tuple[bool, int]:
        n: int = len(chunk) - start
        to_read: int = self.expected - self.read
        if to_read < n:
            self.data.append(chunk[start:to_read])
            return False, to_read
        elif to_read == n:
            self.data.append(chunk[start:] if start else chunk)
            return False, n
        else:
            self.data.append(chunk[start:] if start else chunk)
            return True, n


class HTTPParserStatus(Enum):
    """Represents the completion state of the http parser."""

    Request = 0
    Headers = 1
    Body = 2
    Complete = 2


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

    def feed(self, chunk: bytes) -> Iterator[HTTPParserStatus]:
        size: int = len(chunk)
        o: int = 0
        while o < size:
            l, n = self.parser.feed(chunk, o)
            if l is not None:
                if self.parser is self.request:
                    yield HTTPParserStatus.Request
                    self.parser = self.headers.reset()
                elif self.parser is self.headers:
                    if l is False:
                        yield HTTPParserStatus.Headers
                        if self.request.method not in self.HAS_BODY:
                            yield HTTPParserStatus.Complete
                        else:
                            match self.headers.contentLength:
                                case None:
                                    self.parser = self.bodyEOS.reset(b"\n")
                                    yield HTTPParserStatus.Body
                                case int(n):
                                    self.parser = self.bodyLength.reset(n)
                                    yield HTTPParserStatus.Body
                elif self.parser is self.bodyEOS:
                    yield HTTPParserStatus.Complete
                    self.parser = self.headers.reset()
                elif self.parser is self.bodyLength:
                    yield HTTPParserStatus.Complete
                    self.parser = self.request.reset()
                else:
                    raise RuntimeError(f"Unsupported parser: {self.parser}")
            o += n
            if not n:
                print("Not sure this is good", o)
                raise NotImplementedError


# EOF
