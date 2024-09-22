import asyncio
from extra.client import HTTPClient, pooling


# NOTE: Start "examples/sse.py"
async def main(path: str, host: str = "127.0.0.1", port: int = 8000, ssl: bool = False):
    print(f"Connecting to {host}:{port}{path}")
    # NOTE: Connection pooling does not seem to be working
    with pooling(idle=3600):
        for _ in range(n := 5):
            async for atom in HTTPClient.Request(
                host=host,
                method="GET",
                port=port,
                path=path,
                timeout=10.0,
                streaming=False,
                # NOTE: If you se this to False and you get pooling,
                # you'll get a Connection lost, which is expected.
                keepalive=_ < n - 1,
                ssl=ssl,
            ):
                pass
                # print("   >>> ", atom)
            await asyncio.sleep(0.25)


if __name__ == "__main__":
    import sys

    args = sys.argv[1:] or ["/index"]
    n = len(args)
    print(
        asyncio.run(
            main(
                path=args[0],
                host=args[1] if n > 1 else "127.0.0.1",
                port=int(args[2]) if n > 2 else 8000,
            )
        )
    )
# EOF
