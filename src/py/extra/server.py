import asyncio, os
from typing import Callable, NamedTuple, Any, Coroutine
from enum import Enum
from inspect import iscoroutine
import socket

from .utils.logging import exception
from .model import Application, Service, mount
from .http.model import HTTPRequest, HTTPResponse, HTTPResponseBlob
from .http.parser import HTTPParser, HTTPRequestStatus
from .config import HOST, PORT


class ServerOptions(NamedTuple):
    host: str = "0.0.0.0"
    port: int = 8000
    backlog: int = 10_000
    timeout: float = 10.0
    readsize: int = 4_096
    condition: Callable[[], bool] | None = None


SERVER_ERROR: bytes = (
    b"HTTP/1.1 500 Internal Server Error\r\n"
    b"Content-Type: text/plain\r\n"
    b"Content-Length: 21\r\n"
    b"Connection: close\r\n"
    b"\r\n"
    b"Internal server error\r\n"
)

# class Pools(NamedTuple):
#     requests:list[HTTPRequest]
#     parsers:list[HTTPParser]


# NOTE: Based on benchmarks, this gave the best performance.
class AIOSocket:
    """AsyncIO backend using sockets directly."""

    @staticmethod
    async def AWorker(
        app: Application,
        client: socket.socket,
        *,
        loop: asyncio.AbstractEventLoop,
        options: ServerOptions,
    ):
        """Asynchronous worker, processing a socket in the context
        of an application."""
        sent: bool = False
        try:
            parser: HTTPParser = HTTPParser()
            size: int = options.readsize
            status = HTTPRequestStatus.Processing

            # TODO: Support keep-alive
            # TODO: We should loop and leave the connection open if we're
            # in keep-alive mode.
            buffer = bytearray(size)
            # --
            # NOTE: With HTTP pipelining, multiple requests may be sent
            # without waiting for the server response.
            req: HTTPRequest | None = None
            while req is None and status is HTTPRequestStatus.Processing:
                try:
                    n = await asyncio.wait_for(
                        loop.sock_recv_into(client, buffer), timeout=options.timeout
                    )
                except TimeoutError:
                    status = HTTPRequestStatus.Timeout
                    break
                if not n:
                    status = HTTPRequestStatus.NoData
                    break
                for atom in parser.feed(buffer[:n] if n != size else buffer):
                    if atom is HTTPRequestStatus.Complete:
                        status = atom
                    elif isinstance(atom, HTTPRequest):
                        req = atom
            # NOTE: We'll need to think about the loading of the body, which
            # should really be based on content length. It may be in memory,
            # it may be spooled, or it may be streamed. There should be some
            # update system as well.
            if not req:
                # We did not get a full request
                pass
            else:
                r: HTTPResponse | Coroutine[Any, HTTPResponse, Any] = app.process(req)
                res: HTTPResponse | None = None
                if isinstance(r, HTTPResponse):
                    res = r
                else:
                    res = await r
                if res is None:
                    # TODO: Internal error
                    pass
                else:
                    # We send the request head
                    await loop.sock_sendall(client, res.head())
                    sent = True
                    # And send the request
                    if isinstance(res.body, HTTPResponseBlob):
                        await loop.sock_sendall(client, res.body.payload)
                    else:
                        pass
        except Exception as e:
            exception(e)
        finally:
            if not sent:
                try:
                    await loop.sock_sendall(client, SERVER_ERROR)
                except Exception as e:
                    exception(e)
            # FIXME: We should support keep-alive, where we don't close the
            # connection right away. However the drawback is that each worker
            # is going to linger for longer, waiting for the reader to timeout.
            # By default, connections in HTTP/1.1 are keep alive.
            client.close()

    @classmethod
    async def ARun(
        cls,
        app: Application,
        options: ServerOptions = ServerOptions(),
    ):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((options.host, options.port))
        # The argument is the backlog of connections that will be accepted before
        # they are refused.
        server.listen(options.backlog)
        # This is what we need to use it with asyncio
        server.setblocking(False)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()

        # TODO: Add condition
        try:
            while True:
                try:
                    client, _ = await loop.sock_accept(server)
                except OSError as e:
                    # This can be: [OSError] [Errno 24] Too many open files
                    exception(e)
                # NOTE: Should do something with the tasks
                loop.create_task(cls.AWorker(app, client, loop=loop, options=options))
        finally:
            server.close()


def run(
    *components: Application | Service,
    host: str = HOST,
    port: int = PORT,
    backlog: int = 10_000,
    condition: Callable | None = None,
    timeout: float = 10.0,
):
    options = ServerOptions(
        host=host, port=port, backlog=backlog, condition=condition, timeout=timeout
    )
    app = mount(*components)
    asyncio.run(AIOSocket.ARun(app, options))


# EOF
