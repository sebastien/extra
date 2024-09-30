import asyncio
from extra.client import HTTPClient
from extra.http.model import HTTPBodyBlob

import zlib


class GzipDecoder:
    def __init__(self):
        self.decompressor = zlib.decompressobj(wbits=zlib.MAX_WBITS | 32)
        self.buffer = io.BytesIO()

    def feed(self, chunk: bytes) -> bytes | None:
        return self.decompressor.decompress(chunk)

    def flush(self) -> bytes | None:
        return self.decompressor.flush()


# NOTE: Start "examples/sse.py"
async def main(path: str, host: str = "127.0.0.1", port: int = 443, ssl: bool = True):
    transform = GzipDecoder()

    with open("/dev/stdout", "wb") as f:
        async for atom in HTTPClient.Request(
            host=host,
            method="GET",
            port=port,
            path=path,
            timeout=11.0,
            streaming=False,
            headers={"Accept-Encoding": "gzip"},
            ssl=ssl,
        ):
            if isinstance(atom, HTTPBodyBlob):
                f.write(transform.feed(atom.payload) or b"")
        f.write(transform.flush() or b"")


if __name__ == "__main__":
    import sys

    args = sys.argv[2:] or ["/index"]
    n = len(args)
    asyncio.run(
        main(
            path="/gh/lodash/lodash/4.17.15-npm/lodash.min.js",
            host="cdn.statically.io",
        )
    )
# EOF
