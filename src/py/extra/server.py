import asyncio, os
from typing import Callable, NamedTuple, Any, Coroutine
from enum import Enum
from inspect import iscoroutine
import socket


from .utils.logging import exception, info, warning
from .utils.io import asWritable
from .utils.primitives import TPrimitive
from .utils.limits import LimitType, unlimit
from .model import Application, Service, mount
from .http.model import (
    HTTPRequest,
    HTTPResponse,
    HTTPResponseStream,
    HTTPResponseAsyncStream,
    HTTPResponseBlob,
    HTTPResponseFile,
)
from .http.parser import HTTPParser, HTTPRequestStatus
from .config import HOST, PORT


class ServerOptions(NamedTuple):
    host: str = "0.0.0.0"
    port: int = 8000
    backlog: int = 10_000
    timeout: float = 10.0
    readsize: int = 4_096
    condition: Callable[[], bool] | None = None


SERVER_OK: bytes = (
    b"HTTP/1.1 200 OK\r\n"
    b"Content-Type: text/plain\r\n"
    b"Content-Length: 2\r\n"
    b"Connection: close\r\n"
    b"\r\n"
    b"OK\r\n"
)

SERVER_NOCONTENT: bytes = b"HTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n"
SERVER_ERROR: bytes = (
    b"HTTP/1.1 500 Internal Server Error\r\n"
    b"Content-Type: text/plain\r\n"
    b"Content-Length: 39\r\n"
    b"Connection: close\r\n"
    b"\r\n"
    b"Internal server error: Request not sent\r\n"
)


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
        try:
            parser: HTTPParser = HTTPParser()
            size: int = options.readsize

            # TODO: Support keep-alive
            # TODO: We should loop and leave the connection open if we're
            # in keep-alive mode.
            buffer = bytearray(size)
            # NOTE: Keepalive timeout should be relative to the time it takes
            # to process a request, and to the backlog size as well.
            keep_alive_timeout: float = 2.0
            keep_alive: bool = True
            iteration: int = 0
            while keep_alive:
                status: HTTPRequestStatus = HTTPRequestStatus.Processing
                sent: bool = False
                read_count: int = 0
                # --
                # NOTE: With HTTP pipelining, multiple requests may be sent
                # without waiting for the server response.
                req: HTTPRequest | None = None
                while req is None and status is HTTPRequestStatus.Processing:
                    try:
                        n = await asyncio.wait_for(
                            loop.sock_recv_into(client, buffer),
                            timeout=keep_alive_timeout,
                        )
                        read_count += n
                    except TimeoutError:
                        status = HTTPRequestStatus.Timeout
                        keep_alive_timeout = False
                        break
                    if not n:
                        status = HTTPRequestStatus.NoData
                        break
                    for atom in parser.feed(buffer[:n] if n != size else buffer):
                        if atom is HTTPRequestStatus.Complete:
                            status = atom
                        elif isinstance(atom, HTTPRequest):
                            req = atom
                    del buffer[:n]

                # NOTE: We'll need to think about the loading of the body, which
                # should really be based on content length. It may be in memory,
                # it may be spooled, or it may be streamed. There should be some
                # update system as well.
                if (
                    status is HTTPRequestStatus.Timeout
                    or status is HTTPRequestStatus.NoData
                ):
                    if read_count:
                        warning(
                            "Client did not finish sending a request",
                            ReadCount=read_count,
                            Status=status.name,
                        )
                    break
                elif req is None:
                    warning(
                        "Client did not send a request",
                        ReadCount=read_count,
                        Status=status.name,
                    )
                else:
                    if (
                        req.protocol == "HTTP/1.0"
                        or req.headers.get("connection") == "close"
                    ):
                        keep_alive = False
                    r: HTTPResponse | Coroutine[Any, HTTPResponse, Any] = app.process(
                        req
                    )
                    res: HTTPResponse | None = None
                    if isinstance(r, HTTPResponse):
                        res = r
                    else:
                        res = await r
                    if res is None:
                        warning(
                            "Application did not return a response",
                            Method=req.method,
                            Path=req.path,
                        )
                        await loop.sock_sendall(client, SERVER_NOCONTENT)
                        sent = True
                    else:
                        try:
                            # We send the request head
                            await loop.sock_sendall(client, res.head())
                            sent = True
                            # And send the request
                            if isinstance(res.body, HTTPResponseBlob):
                                await loop.sock_sendall(client, res.body.payload)
                            elif isinstance(res.body, HTTPResponseFile):
                                with open(res.body.path, "rb") as f:
                                    await loop.sock_sendfile(client, f)
                            elif isinstance(res.body, HTTPResponseStream):
                                # No keep alive with streaming as these are long
                                # lived requests.
                                keep_alive = False
                                try:
                                    for chunk in res.body.stream:
                                        await loop.sock_sendall(
                                            client, asWritable(chunk)
                                        )
                                finally:
                                    res.body.stream.close()
                            elif isinstance(res.body, HTTPResponseAsyncStream):
                                # No keep alive with streaming as these are long
                                # lived requests.
                                try:
                                    async for chunk in res.body.stream:
                                        await loop.sock_sendall(
                                            client, asWritable(chunk)
                                        )
                                        keep_alive = False
                                finally:
                                    await res.body.stream.aclose()
                            elif res.body is None:
                                pass
                            else:
                                raise ValueError(f"Unsupported body format: {res.body}")
                        except BrokenPipeError:
                            # Client did an early close
                            sent = True
                        except Exception as e:
                            exception(e)
                    if req._onClose:
                        try:
                            req._onClose(req)
                        except Exception as e:
                            # NOTE: close handler failed
                            exception(e)
                if req and not sent:
                    try:
                        warning(
                            "Server did not send a response",
                            Method=req.method,
                            Path=req.path,
                        )
                        await loop.sock_sendall(client, SERVER_ERROR)
                    except Exception as e:
                        exception(e)
                iteration += 1
        except Exception as e:
            exception(e)
        finally:

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

        tasks: set[asyncio.Task] = set()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()

        info(
            f"Extra AIO Server listening",
            icon="🚀",
            Host=options.host,
            Port=options.port,
        )

        # TODO: Add condition
        try:
            while True:
                try:
                    client, _ = await loop.sock_accept(server)
                    # NOTE: Should do something with the tasks
                    task = loop.create_task(
                        cls.AWorker(app, client, loop=loop, options=options)
                    )
                    tasks.add(task)
                    task.add_done_callback(tasks.discard)
                except OSError as e:
                    # This can be: [OSError] [Errno 24] Too many open files
                    if e.errno == 24:
                        # Implement backpressure or wait mechanism here
                        await asyncio.sleep(0.1)  # Short delay before retrying
                    else:
                        exception(e)

        finally:
            server.close()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


def run(
    *components: Application | Service,
    host: str = HOST,
    port: int = PORT,
    backlog: int = 10_000,
    condition: Callable | None = None,
    timeout: float = 10.0,
):
    unlimit(LimitType.Files)
    options = ServerOptions(
        host=host, port=port, backlog=backlog, condition=condition, timeout=timeout
    )
    app = mount(*components)
    asyncio.run(AIOSocket.ARun(app, options))


# EOF
