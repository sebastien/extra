import asyncio
import os
import sys

RESPONSE = b"""HTTP/1.1 200 OK\r
Content-Type: text/plain\r
Content-Length: 14\r
\r
Hello, World!"""

BACKLOG: int = int(os.getenv("HTTP_BACKLOG", 1_000))
BUFFER: int = int(os.getenv("HTTP_BUFFER", 64_000))
PORT: int = int(os.getenv("HTTP_PORT", 8000))


async def server(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    bufsize: int = BUFFER
    ends: bool = False
    while not ends:
        data: bytes = await reader.read(bufsize)
        ends = len(data) < bufsize
    writer.write(RESPONSE)
    written = await writer.drain()
    writer.close()


def run(host: str = "0.0.0.0", port: int = PORT):
    print(f"AsyncIO HTTP server on {host}:{port}")
    # This the stock AIO processing
    coro = asyncio.start_server(server, host, port, backlog=BACKLOG)
    loop = asyncio.get_event_loop()
    running = loop.run_until_complete(coro)
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    # Close the server
    running.close()
    loop.run_until_complete(running.wait_closed())
    loop.close()


if __name__ == "__main__":
    run()

# EOF
