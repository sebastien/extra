import asyncio, socket, os

# --
# A low-level handler for HTTP requests

RESPONSE = b"""\rHTTP/1.1 200 OK\r
Content-Type: text/plain\r
Content-Length: 12\r
\r
Hello, World!"""

BACKLOG: int = int(os.getenv("HTTP_BACKLOG", 1_000))
BUFFER: int = int(os.getenv("HTTP_BUFFER", 64_000))
PORT: int = int(os.getenv("HTTP_PORT", 8000))

# SOURCE: https://stackoverflow.com/questions/48506460/python-simple-socket-client-server-using-asyncio
async def service_handler(client: socket.socket):
    loop = asyncio.get_event_loop()
    bufsize: int = BUFFER
    ends: bool = False
    # We read the whole request
    while not ends:
        data: bytes = await loop.sock_recv(client, bufsize)
        ends = len(data) < bufsize
    # And send the whole response
    if (err := await loop.sock_sendall(client, RESPONSE)) is not None:
        print("ERROR", err)
    client.close()


async def run(host: str = "0.0.0.0", port: int = PORT):
    print(f"AsyncIO HTTP server on {host}:{port}")
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    # The argument is the backlog of connections that will be accepted before
    # they are refused.
    server.listen(BACKLOG)
    server.setblocking(False)

    loop = asyncio.get_event_loop()

    while True:
        client, _ = await loop.sock_accept(server)
        loop.create_task(service_handler(client))


if __name__ == "__main__":
    asyncio.run(run())
# EOF
