import asyncio
from extra.client import HTTPClient
from extra.http.model import HTTPBodyBlob
from extra.utils.codec import GZipDecoder


# NOTE: Start "examples/sse.py"
async def main(path: str, host: str = "127.0.0.1", port: int = 443, ssl: bool = True):
    transform = GZipDecoder()

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
