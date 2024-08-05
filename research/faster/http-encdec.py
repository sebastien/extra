EOL = b"\r\n"


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


class ChunkedDecoder:
    __slots__ = ["line", "expected"]

    def __init__(self) -> None:
        self.line: list[bytes] = []
        self.expected: int | None = None
        self.read: int = 0

    def reset(self) -> "LineParser":
        self.line.clear()
        self.expected = None
        return self

    def feed(self, chunk: bytes, start: int = 0) -> tuple[list[bytes] | None, int]:
        if self.expected is None:
            line, end = self.line.feed(chunk, start)
            if line is not None:
                # TODO: May fail
                self.expected = int(self.line.flushstr())
                return self.data, (end + 2) - start

    pass
