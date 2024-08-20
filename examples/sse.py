from extra import Service, on, run
from extra.utils.logging import info
from typing import AsyncIterator
import time
import asyncio


class SSE(Service):

    @on(GET="/time")
    @on(GET="/time/{delay:int}")
    def time(self, request, delay: float | int = 1) -> AsyncIterator[str]:
        async def stream():
            """The main streaming function, this is returned as a response
            and will be automatically stopped if the client disconnects."""
            counter = 0
            while counter < 10:
                info(f"SSE stream iteration {counter}")
                yield "event: message\n"
                yield f"date: {time.time()}\n\n"
                await asyncio.sleep(delay)
                counter += 1

        # We register the `onClose` handler that will be called when the
        # client disconnects, or when the iteration stops.
        # FIXME: Should be request.respond().then(XX)
        return request.onClose(lambda _: info(f"SSE stream stopped")).respond(
            stream(), contentType="text/event-stream"
        )

    @on(GET="/chunks")
    def chunks(self, request) -> AsyncIterator[str]:
        # TODO: We should use chunked  encoding for performance, otherwise
        # with the keepalive this will take some time to close.
        def stream():
            """The main streaming function, this is returned as a response
            and will be automatically stopped if the client disconnects."""
            yield "["
            for i in range(10):
                yield str(i)
                yield ","
            yield "10]"

        return request.respond(
            stream(),
            contentType="application/json",
        )


# NOTE: You can start this with `uvicorn sse:app`
app = run(SSE())
# EOF
