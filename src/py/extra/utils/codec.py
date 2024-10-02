import zlib
from typing import Literal
from abc import ABC, abstractmethod


class BytesTransform(ABC):
    """An abstract bytes transform."""

    @abstractmethod
    def feed(self, chunk: bytes, more: bool = False) -> bytes | None | Literal[False]:
        """Feeds bytes to the transform, may return a value."""

    @abstractmethod
    def flush(self) -> bytes | None | Literal[False]:
        """Ensures that the bytes transform is flushed, for chunked encodings this will produce a new chunk."""


class GZipDecoder(BytesTransform):
    __slots__ = ["decompressor"]

    def __init__(self) -> None:
        super().__init__()
        self.decompressor = zlib.decompressobj(wbits=zlib.MAX_WBITS | 32)

    def feed(self, chunk: bytes, more: bool = False) -> bytes | None | Literal[False]:
        return self.decompressor.decompress(chunk)

    def flush(
        self,
    ) -> bytes | None | Literal[False]:
        return self.decompressor.flush()


class GZipEncoder(BytesTransform):
    __slots__ = ["compressor"]

    def __init__(self, compression_level: int = 6) -> None:
        super().__init__()
        self.compressor = zlib.compressobj(
            level=compression_level, wbits=zlib.MAX_WBITS | 16
        )

    def feed(self, chunk: bytes, more: bool = False) -> bytes | None | Literal[False]:
        return self.compressor.compress(chunk)

    def flush(self) -> bytes | None | Literal[False]:
        return self.compressor.flush()


# SEE: https://httpwg.org/specs/rfc9112.html#chunked.encoding
class ChunkedEncoder(BytesTransform):
    __slots__ = ["buffer"]

    def __init__(self) -> None:
        super().__init__()
        self.buffer = bytearray()

    def feed(self, chunk: bytes, more: bool = False) -> bytes | None | Literal[False]:
        if not chunk:
            return None
        self.buffer.extend(chunk)
        return None

    def flush(self) -> bytes | None | Literal[False]:
        if not self.buffer:
            return b"0\r\n\r\n"
        result = f"{len(self.buffer):X}\r\n".encode() + self.buffer + b"\r\n"
        self.buffer.clear()
        return bytes(result)


class ChunkedDecoder(BytesTransform):
    __slots__ = ["buffer", "chunkSize", "readingSize"]

    def __init__(self) -> None:
        super().__init__()
        self.buffer = bytearray()
        self.chunkSize = 0
        self.readingSize = True

    def feed(self, chunk: bytes, more: bool = False) -> bytes | None | Literal[False]:
        self.buffer.extend(chunk)
        # TODO: We should probably reuse the bytes array to avoid more allocations
        res = bytearray()

        while self.buffer:
            if self.readingSize:
                # TODO: Faster to use find
                if b"\r\n" not in self.buffer:
                    break
                size_line, remaining = self.buffer.split(b"\r\n", 1)
                try:
                    self.chunkSize = int(size_line, 16)
                except ValueError:
                    return False  # Invalid chunk size
                self.buffer = remaining
                self.readingSize = False
                if self.chunkSize == 0:
                    return bytes(res) if res else None  # End of chunked data

            if len(self.buffer) < self.chunkSize + 2:
                break

            res.extend(self.buffer[: self.chunkSize])
            self.buffer = self.buffer[self.chunkSize + 2 :]  # +2 for \r\n
            self.readingSize = True

        return bytes(res) if res else None

    def flush(self) -> bytes | None | Literal[False]:
        if self.buffer:
            return False  # Incomplete chunk
        return None


# EOF
