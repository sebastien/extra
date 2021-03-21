from typing import Union, Optional, Callable
import asyncio
import types
import time
from ..model import Service, Application
from ..bridge import mount
from ..logging import logger
from ..protocol import asBytes
from ..protocol.http import HTTPParser, HTTPRequest, HTTPResponse

logging = logger("bridge.aio")


class AIOBridge:

    def __init__(self, app: Application):
        self.app = app

    async def run(self, reader, writer):
        app = self.app
        buffer_size = 256_000
        # We extract meta-information about the connection
        addr = writer.get_extra_info("peername")
        ends = False
        started = time.time()
        # TODO: Turn parser to Flyweight
        parser = HTTPParser(addr, 8080, {})
        # We only parse the REQUEST line and the HEADERS. We'll stop
        # once we reach the body. This means that we won't be reading
        # huge requests large away, but let the client decide how to
        # process them.
        while not ends and parser.step < 2:
            data = await reader.read(buffer_size)
            ends = len(data) < buffer_size
            parser.feed(data)

        # Now that we've parsed the REQUEST and HEADERS, we set the input
        # and let the application do the processing
        parser.input(reader)

        # We initialize the request object
        request = HTTPRequest.Create().init(reader)
        request.protocol = parser.protocol
        request.version = b"1.1"
        request.method = parser.method.decode()
        # TODO: We should split the path and the query
        # NOTE: We need to decode all of that
        request.path = parser.uri.decode()[1:]
        request.query = b"".decode()
        response = app.process(request)

        # TODO: Process the application
        # Here we don't write bodies of HEAD requests, as some browsers
        # simply won't read the body.
        write_body = not (request.method == b"HEAD")

        # We write the response
        writer.write(b"HTTP/1.1 %d\r\n" % (response.status))
        # try:
        #         context.status = int(response_status.split(" ", 1)[0])
        # except:
        #         context.status = 0
        for h, v in response.headers.items():
            writer.write(asBytes(h))
            writer.write(b": ")
            writer.write(asBytes(v))
            writer.write(b"\r\n")
        writer.write(b"Content-Type: text/plain\n")
        writer.write(b"Content-Length: %d\n" % (len(response.bodies[0][0])))
        writer.write(b"\r\n")
        await writer.drain()
        for value, contentType in response.bodies:
            # async for chunk in asChunks(value):
            writer.write(asBytes(value))
        writer.write(b"\r\n")
        await writer.drain()
        await asyncio.sleep(0)

        # bytes_written = 0
        # # NOTE: It's not clear why this returns different types
        # if isinstance(res, types.GeneratorType):
        #     for _ in res:
        #         data = self._ensureBytes(_)
        #         bytes_written += len(data)
        #         if write_body:
        #             writer.write(data)
        # else:
        #     if asyncio.iscoroutine(res):
        #         res = await res
        #     # NOTE: I'm not sure why we need to to asWSGI here
        #     r = res.asWSGI(wrt)
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

        # # We need to let some time for the schedule to do other stuff, this
        # # should prevent the `socket.send() raised exception` errors.
        # # SEE: https://github.com/aaugustin/websockets/issues/84
        # await asyncio.sleep(0)

        # # TODO: The tricky part here is how to interface with WSGI so that
        # # we iterate over the different steps (using await so that we have
        # # proper streaming if the response is an iterator). And also
        # # how to interface with the writing.
        # # NOTE: When the client has closed already
        # #   File "/usr/lib64/python3.6/asyncio/selector_events.py", line 807, in write_eof
        # #     self._sock.shutdown(socket.SHUT_WR)
        # # AttributeError: 'NoneType' object has no attribute 'shutdown'
        if writer._transport and not writer._transport.is_closing():
            try:
                writer.write_eof()
                await writer.drain()
            except OSError as e:
                pass
        writer.close()
        request.recycle()
        # TODO: parser.recycle()


def run(app: Application, address: str = "0.0.0.0", port: int = 8000):
    loop = asyncio.get_event_loop()
    bridge = AIOBridge(app)
    server_coro = asyncio.start_server(
        bridge.run, address, port, loop=loop, backlog=100_000)
    server = loop.run_until_complete(server_coro)
    socket = server.sockets[0].getsockname()
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    # Close the server
    server.close()
    # TODO: This should be joins
    loop.run_until_complete(server.wait_closed())
    loop.run_until_complete(app.stop())
    loop.close()
    logging.trace("done")


def server(*services: Union[Application, Service]) -> Callable:
    app = mount(*services)
    return app

# EOF
