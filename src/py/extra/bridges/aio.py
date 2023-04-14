import time
from asyncio import StreamReader, StreamWriter, sleep, start_server, get_event_loop
from typing import Union
from inspect import iscoroutine
from ..model import Application, Service
from ..bridges import mount
from ..logging import error, operation
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
        started: float = time.time()
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
        request = HTTPRequest.Create().init(
            # FIXME: We should parse the uri
            reader,
            method=http_parser.method,
            path=http_parser.uri,
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
            write_body: bool = not (http_parser.method == "HEAD")

            bytes_written: int = 0
            for chunk in response.write():
                if writer.is_closing():
                    break
                else:
                    writer.write(chunk)
                await writer.drain()

        # for body, content_type in reponse.bodies:
        #     writer.write(body)
        # # NOTE: It's not clear why this returns different types
        # if isinstance(body, types.GeneratorType):
        #     for chunk in body:
        #         data = self._ensureBytes(chunk)
        #         bytes_written += len(data)
        #         if write_body:
        #             writer.write(data)
        # else:
        #     if asyncio.iscoroutine(body):
        #         res = cast(bytes, await body)
        #     # NOTE: I'm not sure why we need to to asWSGI here
        #     # r = res.asWSGI(wrt)
        #     for _ in r:
        #         if isinstance(_, types.AsyncGeneratorType):
        #             async for v in _:
        #                 data = self._ensureBytes(v)
        #                 written += len(data)
        #                 if writer._transport.is_closing():
        #                     break
        #                 if write_body:
        #                     writer.write(data)
        #         else:
        #             data = self._ensureBytes(_)
        #             written += len(data)
        #             if writer._transport.is_closing():
        #                 break
        #             if write_body:
        #                 writer.write(data)
        #         if writer._transport.is_closing():
        #             break

        # We need to let some time for the schedule to do other stuff, this
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
                reader,
                writer,
            )
        except ConnectionResetError as e:
            print("Connection error")
        except Exception as e:
            onException(e)
            raise e


def onLoopException(loop, context):
    onException(context.get("exception", context["message"]))


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
        print(
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
    loop.run_until_complete(app.start())


# EOF
