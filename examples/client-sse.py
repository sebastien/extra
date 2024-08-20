import asyncio
from extra.client import HTTPClient


# NOTE: Start "examples/sse.py"
async def main():
    async for atom in HTTPClient.Request(
        host="127.0.0.1",
        method="GET",
        port=8001,
        path="/time/5",
        timeout=10.0,
        streaming=True,
        ssl=False,
    ):
        print("   >>> ", atom)


print(asyncio.run(main()))
# EOF
