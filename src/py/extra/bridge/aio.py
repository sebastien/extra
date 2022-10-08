import asyncio
import types
import time
from asyncio import StreamReader, StreamWriter
from typing import Callable, Union
from ..model import Application, Service
from ..bridge import mount
from ..logging import error
from ..protocol.http import HTTPRequest, HTTPParser

BAD_REQUEST = b"""\
HTTP1/1 400 Bad Request\r
Content-Length: 0\r
\r
"""


class AIOBridge:
    async def process(
        self, application: Application, reader: StreamReader, writer: StreamWriter
    ):
        # --
        # We extract meta-information about the connection
        addr: str = writer.get_extra_info("peername")
        bufsize: int = 256_000
        ends: bool = False
        started = time.time()
        # FIXME: Port should be sourced elsewhere
        http_parser = HTTPParser(addr, 8080, {})
        read: int = 0
        # --
        # We only parse the REQUEST line and the HEADERS. We'll stop
        # once we reach the body. This means that we won't be reading
        # huge requests right away, but let the client decide how to
        # process them.
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
        )
        if http_parser.rest:
            read += len(http_parser.rest)
            request.feed(http_parser.rest)
        if request.isInitialized:
            writer.write(BAD_REQUEST)
        else:

            # TODO: We'll need to process the request
            response = application.process(request)

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
        await asyncio.sleep(0)

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

    def __init__(self, application: Application, host="0.0.0.0", port=8000):
        self.host: str = host
        self.port: int = port
        self.app: Application = application

    async def request(self, reader, writer):
        bridge: AIOBridge = AIOBridge()
        try:
            await bridge.process(
                self.app,
                reader,
                writer,
            )
        except ConnectionResetError as e:
            print("Connection error")


def run(
    *services: Union[Application, Service],
    host: str = "0.0.0.0",
    port: int = 8000,
    backlog: int = 10_000,
):
    """Runs the given services/application using the embedded AsyncIO HTTP server."""
    loop = asyncio.get_event_loop()
    aio_server = AIOServer(mount(*services), host, port)
    # This the stock AIO processing
    coro = asyncio.start_server(aio_server.request, host, port, backlog=backlog)
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
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    # Close the server
    server.close()
    loop.run_until_complete(server.wait_closed())
    loop.close()


# EOF
