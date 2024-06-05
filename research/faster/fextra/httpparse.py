from typing import Iterator, NamedTuple

# NOTE: Headers as strings, not bytes, it's all ASCII.

# This is a simple HTTP parser based on mini composable parsers (request,
# headers and specialized body). The all work so that they can be fed data.
from io import BytesIO


EOL: bytes = b"\r\n"


class RequestLine(NamedTuple):
    method: str
    path: str
    protocol: str


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


class LineIOParser:
    __slots__ = ["data", "eol", "written"]

    def __init__(self) -> None:
        self.data: BytesIO = BytesIO()
        self.eol: bytes = EOL
        self.written: int = 0

    def reset(self, eol: bytes = EOL) -> "LineIOParser":
        self.data.seek(0)
        self.written = 0
        return self

    def flushstr(self) -> str:
        self.data.seek(0)
        res = self.data.read(self.written).decode("ascii")
        self.reset()
        return res

    def feed(self, chunk: bytes, start: int = 0) -> tuple[BytesIO | None, int]:
        end = chunk.find(self.eol, start)
        n = len(chunk)
        if end == -1:
            w = n - start
            self.data.write(chunk[start:] if start else chunk)
            self.written += w
            return None, w
        else:
            self.data.write(chunk[start:end])
            w = end - start
            self.written += w
            return self.data, w + 2


class RequestParser:

    __slots__ = ["line"]

    def __init__(self) -> None:
        self.line: LineParser = LineParser()

    def reset(self) -> "RequestParser":
        self.line.reset()
        return self

    def feed(self, chunk: bytes, start: int = 0) -> tuple[RequestLine | None, int]:
        chunks, end = self.line.feed(chunk, start)
        if chunks:
            # NOTE: This is safe
            l = b"".join(chunks).decode("ascii")
            i = l.find(" ")
            j = l.rfind(" ")
            return RequestLine(l[0:i], l[i + 1 : j], l[j + 1 :]), end
        else:
            return None, end


class HeaderParser:

    __slots__ = ["previous", "headers", "contentType", "contentLength", "line"]

    def __init__(self) -> None:
        super().__init__()
        self.headers: dict[str, str] = {}
        self.line: LineParser = LineParser()
        self.contentType: str | None = None
        self.contentLength: int | None = None
        # TODO: Close header
        # self.close:bool = False

    def reset(self) -> "HeaderParser":
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
                h = l[:i].strip()
                v = l[i + 1 :].strip()
                self.headers[h] = v.strip()
                return True, end
            else:
                return None, end
        else:
            # An empty line denotes the end of headers
            return False, end


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


import bz2, time
from pathlib import Path


# if __name__ == "__main__":
if True:
    BASE: Path = Path(__file__).absolute().parent.parent.parent.parent

    # NOTE: requests are separated by a `\n`
    with bz2.open(BASE / "data/csic_2010-normalTrafficTraining.txt.bz2") as f:
        request_parser = RequestParser()
        header_parser = HeaderParser()
        body_length_parser = BodyLengthParser()
        body_eos_parser = BodyEOSParser()
        parser: RequestParser | HeaderParser | BodyLengthParser | BodyEOSParser = (
            request_parser
        )
        size = 2048
        i = 0
        print("\n\n==============")
        t = time.monotonic()
        count = 0
        total: int = 0
        while True:
            o: int = 0
            chunk: bytes = f.read(size)
            if not chunk:
                break
            while o < size:
                l, n = parser.feed(chunk, o)
                # print(
                #     f"Chunk {repr(chunk[o:o+n])}={l} from {parser.__class__.__name__}"
                # )
                if l is not None:
                    if parser is request_parser:
                        parser = header_parser.reset()
                    elif parser is header_parser:
                        if l is False:
                            if header_parser.contentLength is None:
                                parser = body_eos_parser.reset(b"\n")
                            else:
                                parser = body_length_parser.reset(
                                    header_parser.contentLength
                                )
                    elif parser is body_eos_parser:
                        parser = request_parser.reset()
                    elif parser is body_length_parser:
                        parser = request_parser.reset()

                    count += 1
                o += n
                if not n:
                    break
            total += len(chunk)
            i += 1
        elapsed = time.monotonic() - t
        # ## With a bzip2 source:
        # Reading chunks:
        #  - 37.45Mb/s size=2048
        # Reading lines:
        # - 24.12Mb/s size=2048
        # Reading lines, headers & bodies:
        # - 14.41Mb/s (Py3.12)
        # - 15.11Mb/s (MyPyC)
        # - 21.14Mb/s (PyPy)
        # ## With a text source:
        # Reading lines, headers & bodies:
        # - 25.76Mb/s (Py3.12)
        # - 28.14Mb/s (MyPyC)
        # - 86.96Mb/s (PyPy)

        print(
            f"Elapsed: {count}/{elapsed:0.2f}s through={(total/1_000_000)/elapsed:0.2f}Mb/s size={size} count={count}"
        )

# EOF
