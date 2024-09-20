from typing import Iterator, ClassVar, Literal
from ..utils.io import LineParser, EOL
from .model import (
    HTTPRequest,
    HTTPResponse,
    HTTPRequestLine,
    HTTPResponseLine,
    HTTPHeaders,
    HTTPBodyBlob,
    HTTPAtom,
    HTTPProcessingStatus,
    headername,
)


class MessageParser:

    __slots__ = ["line", "value"]

    def __init__(self) -> None:
        self.line: LineParser = LineParser()
        self.value: HTTPRequestLine | HTTPResponseLine | None = None

    def flush(self) -> "HTTPRequestLine|HTTPResponseLine|None":
        res = self.value
        self.reset()
        return res

    def reset(self) -> "MessageParser":
        self.line.reset()
        self.value = None
        return self

    def feed(self, chunk: bytes, start: int = 0) -> tuple[bool | None, int]:
        line, read = self.line.feed(chunk, start)
        if line:
            # NOTE: This is safe
            l = line.decode("ascii")
            if l.startswith("HTTP/"):
                protocol, status, message = l.split(" ", 2)
                self.value = HTTPResponseLine(
                    protocol,
                    int(status),
                    message,
                )
            else:
                i = l.find(" ")
                j = l.rfind(" ")
                p: list[str] = l[i + 1 : j].split("?", 1)
                # NOTE: There may be junk before the method name
                self.value = HTTPRequestLine(
                    l[0:i], p[0], p[1] if len(p) > 1 else "", l[j + 1 :]
                )
            return True, read
        else:
            return None, read

    def __str__(self) -> str:
        return f"MessageParser({self.value})"


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

    def flush(self) -> "HTTPHeaders|None":
        res = HTTPHeaders(self.headers, self.contentType, self.contentLength)
        self.reset()
        return res

    def reset(self) -> "HeadersParser":
        self.line.reset()
        self.headers = {}
        self.contentType = None
        self.contentLength = None
        return self

    def feed(
        self, chunk: bytes, start: int = 0
    ) -> tuple[str | Literal[False] | None, int]:
        """Feeds data from chunk, starting at `start` offset. Returns
        a value and the next start offset. When the value is `None`, no
        header has been extracted, when the value is `False` it's an empty
        line, and when the value is `True`, a header was added."""
        chunks, read = self.line.feed(chunk, start)
        if chunks is None:
            return None, read
        elif chunks:
            line: bytes | None = self.line.flush()
            if line is None:
                return False, read
            # Headers are expected to be in ASCII format
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
                n: str = headername(h)
                self.headers[n] = v
                # We have parsed a full header, we return True
                return n, read
            else:
                return None, read
        else:
            # An empty line denotes the end of headers
            return False, read

    def __str__(self) -> str:
        return f"HeadersParser({self.headers})"


class BodyEOSParser:

    __slots__ = ["line", "data"]

    def __init__(self) -> None:
        self.line = LineParser()
        self.data: bytes | None = None

    def flush(self) -> HTTPBodyBlob:
        # TODO: We should check it's expected
        res = (
            HTTPBodyBlob(
                self.data,
                len(self.data),
            )
            if self.data is not None
            else HTTPBodyBlob()
        )
        self.reset()
        return res

    def reset(self, eos: bytes = EOL) -> "BodyEOSParser":
        self.line.reset(eos)
        self.data = None
        return self

    def feed(self, chunk: bytes, start: int = 0) -> tuple[bytes | None, int]:
        line, read = self.line.feed(chunk, start)
        if line is None:
            return None, read
        else:
            data = self.line.flush()
            return data, read


class BodyLengthParser:
    """Parses the body of a request with ContentLength set"""

    __slots__ = ["expected", "read", "data"]

    def __init__(self) -> None:
        self.expected: int | None = None
        self.read: int = 0
        self.data: list[bytes] = []

    def flush(self) -> HTTPBodyBlob:
        # TODO: We should check it's expected
        res = HTTPBodyBlob(
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
        # FIXME: Is this correct?
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

    METHOD_HAS_BODY: ClassVar[set[str]] = {"POST", "PUT", "PATCH"}

    def __init__(self) -> None:
        self.message: MessageParser = MessageParser()
        self.headers: HeadersParser = HeadersParser()
        self.bodyEOS: BodyEOSParser = BodyEOSParser()
        self.bodyLength: BodyLengthParser = BodyLengthParser()
        self.parser: (
            MessageParser | HeadersParser | BodyEOSParser | BodyLengthParser
        ) = self.message
        self.requestLine: HTTPRequestLine | HTTPResponseLine | None = None
        self.requestHeaders: HTTPHeaders | None = None

    def feed(self, chunk: bytes) -> Iterator[HTTPAtom]:
        # FIXME: Should write to a buffer
        size: int = len(chunk)
        offset: int = 0
        while offset < size:
            # The expectation here is that when we feed a chunk and it's
            # partially read, we don't need to re-feed it again. The underlying
            # parser will keep a buffer up until it is flushed.
            l, read = self.parser.feed(chunk, offset)
            if l is None:
                # NOTE: Keeping for reference here that we
                offset += read
            else:
                if self.parser is self.message:
                    # We've parsed a request line
                    line = self.message.flush()
                    self.requestLine = line
                    self.requestHeaders = None
                    if line is not None:
                        yield line
                        self.parser = self.headers
                elif self.parser is self.headers:
                    if l is False:
                        # We've parsed the headers
                        headers = self.headers.flush()
                        line = self.requestLine
                        self.requestHeaders = headers
                        if headers is not None:
                            yield headers
                        # If it's a method with no expected body, we skip the parsing
                        # of the body.
                        if (
                            self.requestLine
                            and isinstance(self.requestLine, HTTPRequestLine)
                            and (
                                self.requestLine.method not in self.METHOD_HAS_BODY
                                or headers
                                and headers.contentLength == 0,
                            )
                        ):
                            # That's an early exit
                            yield HTTPRequest(
                                method=line.method,
                                path=line.path,
                                query=parseQuery(line.query),
                                headers=headers or HTTPHeaders({}),
                                protocol=line.protocol,
                                body=HTTPBodyBlob(b"", 0),
                            )
                            self.parser = self.message.reset()
                        elif headers is not None:
                            if headers.contentLength is None:
                                self.parser = self.bodyEOS.reset(b"\n")
                                yield HTTPProcessingStatus.Body
                            else:
                                self.parser = self.bodyLength.reset(
                                    headers.contentLength
                                )
                                yield HTTPProcessingStatus.Body
                elif self.parser is self.bodyEOS or self.parser is self.bodyLength:
                    if line is None or headers is None:
                        yield HTTPProcessingStatus.BadFormat
                    else:
                        headers = headers or HTTPHeaders({})
                        # NOTE: This is an awkward dance around the type checker
                        body = (
                            self.bodyEOS.flush()
                            if self.parser is self.bodyEOS
                            else self.bodyLength.flush()
                        )
                        yield (
                            HTTPRequest(
                                method=line.method,
                                protocol=line.protocol,
                                path=line.path,
                                query=parseQuery(line.query),
                                headers=headers,
                                # NOTE: This is an awkward dance around the type checker
                                body=body,
                            )
                            if isinstance(line, HTTPRequestLine)
                            else HTTPResponse(
                                protocol=line.protocol,
                                status=line.status,
                                message=line.message,
                                headers=headers,
                                body=body,
                            )
                        )
                    self.parser = self.message.reset()
                else:
                    raise RuntimeError(f"Unsupported parser: {self.parser}")
            # We increase the offset with the read bytes
            offset += read


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
