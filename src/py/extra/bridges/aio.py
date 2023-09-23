from asyncio import (
    StreamReader,
    StreamWriter,
    sleep,
    start_server,
    get_event_loop,
    all_tasks,
    gather,
)
from typing import Union, Optional
from inspect import iscoroutine
import socket
from ..model import Application, Service
from ..bridges import mount
from ..logging import error, operation, log, info
from ..protocols.http import HTTPRequest, HTTPParser, BAD_REQUEST
from ..utils.hooks import onException
from ..utils.config import HOST, PORT


class AIOBridge:
    async def process(
        self, application: Application, reader: StreamReader, writer: StreamWriter
    ):
        # --
        # We extract meta-information about the connection
        addr: str = writer.get_extra_info("peername")
        bufsize: int = 256_000
        ends: bool = False
        # FIXME: Port should be sourced elsewhere
        http_parser: HTTPParser = HTTPParser(addr, PORT, {})
        read: int = 0
        # We only parse the REQUEST line and the HEADERS. We'll stop
        # once we reach the body. This means that we won't be reading
        # huge requests right away, but let the client decide how to
        # process them.
        #
        # NOTE: We may have read the whole request in the buffer,
        # `http_parser.rest` will contain the rest, which my be all.
        while not (ends or http_parser.hasReachedBody):
            data: bytes = await reader.read(bufsize)
            n: int = len(data)
            read += n
            ends = n < bufsize
            if not http_parser.feed(data):
                break

        # --
        # Now that we've parsed the REQUEST and HEADERS, we set the input
        # and let the application do the processing
        # --
        # FIXME: We may have read past the body, so we should feed the
        # first part
        log(f"[{http_parser.method}] {http_parser.uri}")
        t: str = http_parser.uri or ""
        la: list[str] = t.rsplit("#", 1)
        uri_hash: Optional[str] = la[1] if len(la) == 2 else None
        lb: list[str] = la[0].rsplit("?", 1)
        uri_query: Optional[str] = lb[1] if len(lb) == 2 else None
        uri_path: str = lb[0]
        request = HTTPRequest.Create().init(
            # FIXME: We should parse the uri
            reader,
            method=http_parser.method,
            path=uri_path,
            query=uri_query,
            hash=uri_hash,
            headers=http_parser.headers,
        )
        if http_parser.rest:
            read += len(http_parser.rest)
            request.feed(http_parser.rest)
        if not request.isInitialized:
            # This is likely an issue with the transport, or maybe the request is bad
            writer.write(BAD_REQUEST)
        else:

            # TODO: We process the request, which may very well be a coroutine
            if iscoroutine(r := application.process(request)):
                response = await r
            else:
                response = r

            # TODO: Process the application
            # Here we don't write bodies of HEAD requests, as some browsers
            # simply won't read the body.
            # write_body: bool = not (http_parser.method == "HEAD")
            # bytes_written: int = 0
            for chunk in response.write():
                if writer.is_closing():
                    break
                else:
                    writer.write(chunk)
                await writer.drain()

        # We need to let some time for the scheduler to do other stuff, this
        # should prevent the `socket.send() raised exception` errors.
        # SEE: https://github.com/aaugustin/websockets/issues/84
        await sleep(0)

        # TODO: The tricky part here is how to interface with WSGI so that
        # we iterate over the different steps (using await so that we have
        # proper streaming if the response is an iterator). And also
        # how to interface with the writing.
        # NOTE: When the client has closed already
        #   File "/usr/lib64/python3.6/asyncio/selector_events.py", line 807, in write_eof
        #     self._sock.shutdown(socket.SHUT_WR)
        # AttributeError: 'NoneType' object has no attribute 'shutdown'
        if not writer.is_closing():
            try:
                writer.write_eof()
                await writer.drain()
            except OSError as e:
                error("AIO/OSERROR", f"Transport draining failed: {e}", origin="aio")
                writer.close()


# TODO: We should build this abstraction
# class AIOReader(Reader, Flyweight["AIOReader"]):
#     def __init__(self):
#         super().__init__()
#         self.reader: Optional[StreamReader] = None
#
#     def init(self, reader: StreamReader) -> "Reader":
#         self.reader = reader
#         return self
#
#     def reset(self) -> "Reader":
#         return self


class AIOServer:
    """A simple asyncio-based asynchronous server"""

    def __init__(self, application: Application, host: str = HOST, port: int = PORT):
        self.host: str = host
        self.port: int = port
        self.app: Application = application

    async def request(self, reader: StreamReader, writer: StreamWriter):
        bridge: AIOBridge = AIOBridge()
        try:
            await bridge.process(
                self.app,
                # TODO: Wrap reader/writer ther
                reader,
                writer,
            )
        except ConnectionResetError as e:
            error("ECONN", f"AIOServer.request: Connection error {e}")
        except Exception as e:
            onException(e)
            raise e


def onLoopException(loop, context):
    onException(context.get("exception", context["message"]))


# TODO: start() should generate a corouting
async def arun(
    *components: Union[Application, Service],
    host: str = HOST,
    port: int = PORT,
    backlog: int = 10_000,
):
    app = mount(*components)
    aio_server = AIOServer(app, host, port)
    # This the stock AIO processing
    server = await start_server(
        aio_server.request, host, port, backlog=backlog, limit=2**16
    )
    if sock := server.get_extra_info("socket"):
        # We'll likely be streaming, so we send keepalives
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        # We're streaming so we want to reduce latency
        # <<<Enabling TCP_NODELAY turns off this delay mechanism, which can be
        # useful in situations where you need low latency and want to minimize
        # the delay in sending small packets. Real-time applications like
        # online gaming or video conferencing often benefit from this
        # option.>>> (GPT4)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, True)
    socket_name = server.sockets[0].getsockname()
    info(
        "Extra {font_server}AIO{reset} server listening on {font_url}http://{host}:{port}{reset}".format(
            host=socket_name[0],
            port=socket_name[1],
            font_server="",
            font_url="",
            reset="",
        )
    )
    # if server:
    #     with operation("Closing server"):
    #         server.close()
    #         try:
    #             loop.run_until_complete(server.wait_closed())
    #         except KeyboardInterrupt:
    #             pass
    #         finally:
    #             loop.close()
    # # Waits up until the app has finished
    # loop.run_until_complete(app.stop())
    await app.stop()
    return app


def run(
    *components: Union[Application, Service],
    host: str = HOST,
    port: int = PORT,
    backlog: int = 10_000,
):
    """Runs the given services/application using the embedded AsyncIO HTTP server."""
    loop = get_event_loop()
    # TODO: This does not seem to work
    loop.set_exception_handler(onLoopException)
    app = mount(*components)
    loop.run_until_complete(app.start())
    aio_server = AIOServer(app, host, port)
    # This the stock AIO processing
    coro = start_server(aio_server.request, host, port, backlog=backlog)
    server = None
    try:
        server = loop.run_until_complete(coro)
        socket = server.sockets[0].getsockname()
        info(
            "Extra {font_server}AIO{reset} server listening on {font_url}http://{host}:{port}{reset}".format(
                host=socket[0],
                port=socket[1],
                font_server="",
                font_url="",
                reset="",
            )
        )
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    if server:
        with operation("Closing server"):
            server.close()
            try:
                loop.run_until_complete(server.wait_closed())
            except KeyboardInterrupt:
                pass
            finally:
                loop.close()
    # Waits up until the app has finished
    try:
        loop.run_until_complete(app.stop())
    except Exception:
        # FIXME: This does not seem to  be working
        for task in all_tasks(loop=loop):
            task.cancel()
        # Run the event loop until all tasks are cancelled
        loop.run_until_complete(gather(*all_tasks(loop=loop), return_exceptions=True))
        # Close the event loop
        loop.close()


# EOF
