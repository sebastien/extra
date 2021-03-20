import asyncio
import types
import time
from ..bridge import mount
from ..logging import error
from ..util.http import HTTPParser


class AIOBridge:

    async def process(self, reader, writer):
        # We extract meta-information about the connection
        addr = writer.get_extra_info("peername")
        bufize = 256_000
        ends = False
        started = time.time()
        context = HTTPParser(addr, 8080, {})
        # We only parse the REQUEST line and the HEADERS. We'll stop
        # once we reach the body. This means that we won't be reading
        # huge requests large away, but let the client decide how to
        # process them.
        while not ends and context.step < 2:
            data = await reader.read(bufsize)
            ends = len(data) < bufsize
            context.feed(data)

        # Now that we've parsed the REQUEST and HEADERS, we set the input
        # and let the application do the processing
        context.input(reader)

        # TODO: Process the application
        # Here we don't write bodies of HEAD requests, as some browsers
        # simply won't read the body.
        write_body = not (context.method == "HEAD")

        bytes_written = 0
        # NOTE: It's not clear why this returns different types
        if isinstance(res, types.GeneratorType):
            for _ in res:
                data = self._ensureBytes(_)
                bytes_written += len(data)
                if write_body:
                    writer.write(data)
        else:
            if asyncio.iscoroutine(res):
                res = await res
            # NOTE: I'm not sure why we need to to asWSGI here
            r = res.asWSGI(wrt)
            for _ in r:
                if isinstance(_, types.AsyncGeneratorType):
                    async for v in _:
                        data = self._ensureBytes(v)
                        written += len(data)
                        if writer._transport.is_closing():
                            break
                        if write_body:
                            writer.write(data)
                else:
                    data = self._ensureBytes(_)
                    written += len(data)
                    if writer._transport.is_closing():
                        break
                    if write_body:
                        writer.write(data)
                if writer._transport.is_closing():
                    break

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
        if writer._transport and not writer._transport.is_closing():
            try:
                writer.write_eof()
                await writer.drain()
            except OSError as e:
                error("aio", "OSERROR", str(e))
                pass
        writer.close()


def server(*services: Union[Application, Service]) -> Callable:
    app = mount(services)

# EOF
