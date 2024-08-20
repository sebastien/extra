from typing import Iterator, ClassVar
from ..utils.io import LineParser, EOL
from .model import (
    HTTPRequest,
    HTTPRequestLine,
    HTTPRequestHeaders,
    HTTPRequestBlob,
    HTTPRequestAtom,
    HTTPRequestStatus,
    headername,
)


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
        line, end = self.line.feed(chunk, start)
        if line:
            # NOTE: This is safe
            l = line.decode("ascii")
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


class ReponseParser:

    __slots__ = ["line", "value"]

    def __init__(self) -> None:
        self.line: LineParser = LineParser()
        self.value: HTTPResponseLine | None = None

    def flush(self) -> "HTTPResponseLine|None":
        res = self.value
        self.value = None
        return res

    def reset(self) -> "ResponseParser":
        self.line.reset()
        self.value = None
        return self

    def feed(self, chunk: bytes, start: int = 0) -> tuple[bool | None, int]:
        line, end = self.line.feed(chunk, start)
        if line:
            # NOTE: This is safe
            l = line.decode("ascii")
            i = l.find(" ")
            j = l.rfind(" ")
            p: list[str] = l[i + 1 : j].split("?", 1)
            # NOTE: There may be junk before the method name
            self.value = HTTPResponseLine(
                l[0:i], p[0], p[1] if len(p) > 1 else "", l[j + 1 :]
            )
            return True, end
        else:
            return None, end

    def __str__(self) -> str:
        return f"ResponseParser({self.value})"


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
            line: bytes | None = self.line.flush()
            if line is None:
                return False, end
            l: str = line.decode("ascii")
            i = l.find(":")
            if i != -1:
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
                self.headers[headername(h)] = v
                return True, end
            else:
                return None, end
        else:
            # An empty line denotes the end of headers
            return False, end

    def __str__(self) -> str:
        return f"HeadersParser({self.headers})"


class BodyEOSParser:

    __slots__ = ["line", "data"]

    def __init__(self) -> None:
        self.line = LineParser()
        self.data: bytes | None = None

    def flush(self) -> HTTPRequestBlob:
        # TODO: We should check it's expected
        res = (
            HTTPRequestBlob(
                self.data,
                len(self.data),
            )
            if self.data is not None
            else HTTPRequestBlob()
        )
        self.reset()
        return res

    def reset(self, eos: bytes = EOL) -> "BodyEOSParser":
        self.line.reset(eos)
        self.data = None
        return self

    def feed(self, chunk: bytes, start: int = 0) -> tuple[bytes | None, int]:
        line, end = self.line.feed(chunk, start)
        if line is None:
            return None, end
        else:
            data = self.line.flush()
            return data, end


class BodyLengthParser:
    """Parses the body of a request with ContentLength set"""

    __slots__ = ["expected", "read", "data"]

    def __init__(self) -> None:
        self.expected: int | None = None
        self.read: int = 0
        self.data: list[bytes] = []

    def flush(self) -> HTTPRequestBlob:
        # TODO: We should check it's expected
        res = HTTPRequestBlob(
            b"".join(self.data),
            self.read,
            0 if self.expected is None else self.expected - self.read,
        )
        self.reset()
        return res

    def reset(self, length: int | None = None) -> "BodyLengthParser":
        self.expected = length
        self.read = 0
        self.data.clear()
        return self

    def feed(self, chunk: bytes, start: int = 0) -> tuple[bool, int]:
        size: int = len(chunk)
        left: int = size - start
        to_read: int = min(
            left, left if self.expected is None else self.expected - self.read
        )
        if to_read < left:
            self.data.append(chunk[start : start + to_read])
            self.read += to_read
            return False, to_read
        else:
            self.data.append(chunk[start:] if start else chunk)
            self.read += to_read
            return True, to_read


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
                            yield HTTPRequest(
                                method=line.method,
                                path=line.path,
                                query=parseQuery(line.query),
                                headers=headers or HTTPRequestHeaders({}),
                                protocol=line.protocol,
                                body=HTTPRequestBlob(b"", 0),
                            )
                            self.parser = self.request.reset()
                        elif headers is not None:
                            if headers.contentLength is None:
                                self.parser = self.bodyEOS.reset(b"\n")
                                yield HTTPRequestStatus.Body
                            else:
                                self.parser = self.bodyLength.reset(
                                    headers.contentLength
                                )
                                yield HTTPRequestStatus.Body
                elif self.parser is self.bodyEOS or self.parser is self.bodyLength:
                    if line is None or headers is None:
                        yield HTTPRequestStatus.BadFormat
                    else:
                        yield HTTPRequest(
                            method=line.method,
                            protocol=line.protocol,
                            path=line.path,
                            query=parseQuery(line.query),
                            headers=headers or HTTPRequestHeaders({}),
                            # NOTE: This is an awkward dance around the type checker
                            body=(
                                self.bodyEOS.flush()
                                if self.parser is self.bodyEOS
                                else self.bodyLength.flush()
                            ),
                        )
                    self.parser = self.request.reset()
                else:
                    raise RuntimeError(f"Unsupported parser: {self.parser}")
            o += n
            if not n:
                print("Not sure this is good", o)
                raise NotImplementedError


def parseQuery(text: str) -> dict[str, str]:
    res: dict[str, str] = {}
    for item in text.split("&"):
        kv = item.split("=", 1)
        if len(kv) == 1:
            res[item] = ""
        else:
            res[kv[0]] = kv[1]
    return res


# EOF
