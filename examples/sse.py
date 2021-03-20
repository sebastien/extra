from extra import Service, Request, Response, on, expose, server, info
from typing import AsyncIterator
import time
import asyncio


class SSE(Service):

    @on(GET="/stream")
    def stream(self, request) -> AsyncIterator[str]:
        async def stream():
            """The main streaming function, this is returned as a response
            and will be automatically stopped if the client disconnects."""
            counter = 0
            while counter < 10:
                info("sse", f"SSE stream iteration {counter}")
                yield "event: message\n"
                yield f"date: {time.time()}\n\n"
                await asyncio.sleep(1)
                counter += 1
        # We register the `onClose` handler that will be called when the
        # client disconnects, or when the iteration stops.
        return request.onClose(
            lambda _: info("sse", "SSE stream stopped", _.status)
        ).respond(stream(), contentType=b"text/plain")


# NOTE: You can start this with `uvicorn sse:app`
app = server(SSE)
# EOF
