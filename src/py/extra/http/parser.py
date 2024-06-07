from typing import Iterator, ClassVar
from .model import (
    HTTPRequest,
    HTTPRequestLine,
    HTTPRequestHeaders,
    HTTPRequestBlob,
    HTTPRequestAtom,
    HTTPRequestStatus,
)


EOL: bytes = b"\r\n"
END: int = 1


class LineParser:
    __slots__ = ["buffer", "line", "eol", "eolsize", "offset"]

    def __init__(self) -> None:
        self.buffer: bytearray = bytearray()
        self.line: str | None = None
        self.offset: int = 0
        self.eol: bytes = EOL
        self.eolsize: int = len(EOL)

    def reset(self, eol: bytes = EOL) -> "LineParser":
        self.buffer.clear()
        self.eol = eol
        self.eolsize = len(eol)
        return self

    def flush(self) -> str | None:
        return self.line

    def feed(self, chunk: bytes, start: int = 0) -> tuple[str | None, int]:
        # We do need to append the whole chunk as we may have the previous chunk
        # be like `***\r`, and then the new one like `\n***`, and in that case we
        # wouldn't match the EOL.
        read: int = len(chunk) - start
        self.buffer += chunk[start:] if start else chunk
        end = self.buffer.find(self.eol, self.offset)
        if end == -1:
            # We haven't found the end pattern yet, so we we're reading the entire buffer
            self.offset += read - (self.eolsize - 1)
            return None, read
        else:
            # We get the resulting line
            self.line = self.buffer[:end].decode("ascii")
            # We get the original position in the buffer, this will
            # tell us how much of the chunk we'll consume.
            pos: int = len(self.buffer) - read
            # We can clear the buffer, we've got a line
            self.buffer.clear()
            # We return the line and how much we've read
            return self.line, (end + len(self.eol)) - pos


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
            i = line.find(" ")
            j = line.rfind(" ")
            p: list[str] = line[i + 1 : j].split("?", 1)
            # NOTE: There may be junk before the method name
            self.value = HTTPRequestLine(
                line[0:i], p[0], p[1] if len(p) > 1 else "", line[j + 1 :]
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
            l = self.line.flush()
            if l is None:
                return False, end
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

    def feed(self, chunk: bytes, start: int = 0) -> tuple[str | None, int]:
        line, end = self.line.feed(chunk, start)
        if line is None:
            return None, end
        else:
            self.line.reset()
            return line, end


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
                            yield HTTPRequestBlob(b"", 0)
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
                            path=line.path,
                            query=line.query,
                            headers=headers,
                            body=self.parser.flush(),
                        )
                    self.parser = self.headers.reset()
                else:
                    raise RuntimeError(f"Unsupported parser: {self.parser}")
            o += n
            if not n:
                print("Not sure this is good", o)
                raise NotImplementedError


# EOF
