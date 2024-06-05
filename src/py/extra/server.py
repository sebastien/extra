import asyncio
from typing import Callable
from enum import Enum
import socket
import multiprocessing

from .http.parser import HTTPParser, HTTPParserStatus


class ServerOptions:
    host: str = "0.0.0.0"
    port: int = 8000
    backlog: int = 10_000
    timeout: float = 10.0
    readsize: int = 4_096
    condition: Callable[[], bool] | None = None


class RequestStatus(Enum):
    Processing = 1
    Complete = 2
    Timeout = 3
    NoData = 4


CANNED_RESPONSE: bytes = (
    b"HTTP/1.1 200 OK\r\n"
    b"Content-Type: text/plain\r\n"
    b"Content-Length: 13\r\n"
    b"\r\n"
    b"Hello, World!\r\n"
)


# NOTE: Based on benchmarks, this gave the best performance.
class AIOSocket:
    """AsyncIO backend using sockets directly."""

    @staticmethod
    async def AWorker(
        client: socket.socket,
        *,
        loop: asyncio.AbstractEventLoop,
        options: ServerOptions,
        parsers: list[HTTPParser] = [],
    ):
        try:
            parser: HTTPParser = parsers.pop() if parsers else HTTPParser()
            size: int = options.readsize
            status = RequestStatus.Processing

            buffer = bytearray(size)
            while status is RequestStatus.Processing:
                try:
                    n = await asyncio.wait_for(
                        loop.sock_recv_into(client, buffer), timeout=options.timeout
                    )
                except TimeoutError:
                    status = RequestStatus.Timeout
                    break
                if not n:
                    status = RequestStatus.NoData
                    break
                for atom in parser.feed(buffer[:n] if n != size else buffer):
                    if atom is HTTPParserStatus.Complete:
                        status = RequestStatus.Complete
            # NOTE: We can do `sock_sendfile` which is super useful for
            await loop.sock_sendall(client, CANNED_RESPONSE)
        except Exception as e:
            print(f"Error handling request: {e}")
        finally:
            client.close()

    @classmethod
    async def ARun(
        cls,
        options: ServerOptions = ServerOptions(),
    ):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((options.host, options.port))
        # The argument is the backlog of connections that will be accepted before
        # they are refused.
        server.listen(options.backlog)
        server.setblocking(False)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()

        # TODO: Add condition
        while True:
            client, _ = await loop.sock_accept(server)
            loop.create_task(cls.AWorker(client, loop=loop, options=options))


if __name__ == "__main__":
    asyncio.run(AIOSocket.ARun())

# EOF
