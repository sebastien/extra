from extra import Service, Request, Response, on, expose, server
from typing import AsyncIterator
import time
import asyncio


# @title SSE Stream

class SSE(Service):

    # service, encoding the results as JSON
    @expose(GET="/stream", contentType=b"text/plain")
    def stream(self) -> AsyncIterator[str]:
        # request.onClose(lambda *args: print("Closing", args))

        async def stream():
            while True:
                yield "event: message\n"
                yield f"date: {time.time()}\n\n"
                await asyncio.sleep(1)
        return stream()


# NOTE: You can start this with `uvicorn sse:app`
app = server(SSE)
# EOF
