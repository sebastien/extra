import asyncio
from extra.client import HTTPClient, pooling


# NOTE: Start "examples/sse.py"
async def main(path: str, host: str = "127.0.0.1", port: int = 8000, ssl: bool = False):
    print(f"Connecting to {host}:{port}{path}")
    # NOTE: Connection pooling does not seem to be working
    with pooling(idle=3600):
        for _ in range(10):
            async for atom in HTTPClient.Request(
                host=host,
                method="GET",
                port=port,
                path=path,
                timeout=10.0,
                streaming=False,
                keepalive=_ < 9,
                ssl=ssl,
            ):
                print("   >>> ", atom)
            await asyncio.sleep(1.0)


if __name__ == "__main__":
    import sys

    args = sys.argv[1:]
    n = len(args)
    print(n, args)
    print(
        asyncio.run(
            main(
                path=args[0],
                host=args[1] if n >= 1 else "127.0.0.1",
                port=int(args[2]) if n >= 2 else 8000,
            )
        )
    )
# EOF
