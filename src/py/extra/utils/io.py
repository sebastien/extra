from typing import NamedTuple
from .json import json
from .primitives import TPrimitive

DEFAULT_ENCODING: str = "utf8"


class Control(NamedTuple):
    id: str


EOS = Control("EOS")


def asBytes(value: str | bytes) -> bytes:
    if isinstance(value, bytes):
        return value
    elif isinstance(value, str):
        return bytes(value, DEFAULT_ENCODING)
    elif value is None:
        return b""
    else:
        raise ValueError(f"Expected bytes or str, got: {value}")


def asWritable(value: str | bytes | TPrimitive) -> bytes:
    if isinstance(value, bytes):
        return value
    elif isinstance(value, str):
        return value.encode(DEFAULT_ENCODING)
    else:
        return json(value)


EOL: bytes = b"\r\n"
END: int = 1


class LineParser:
    __slots__ = ["buffer", "line", "eol", "eolsize", "offset"]

    def __init__(self) -> None:
        self.buffer: bytearray = bytearray()
        self.line: bytes | None = None
        self.offset: int = 0
        self.eol: bytes = EOL
        self.eolsize: int = len(EOL)

    def reset(self, eol: bytes = EOL) -> "LineParser":
        self.buffer.clear()
        self.eol = eol
        self.eolsize = len(eol)
        return self

    def flush(self) -> bytes | None:
        return self.line

    def feed(self, chunk: bytes, start: int = 0) -> tuple[bytes | None, int]:
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
            self.line = self.buffer[:end]
            # We get the original position in the buffer, this will
            # tell us how much of the chunk we'll consume.
            pos: int = len(self.buffer) - read
            # We can clear the buffer, we've got a line
            self.buffer.clear()
            # We return the line and how much we've read
            return self.line, (end + len(self.eol)) - pos


# EOF
