from ..protocol import Request, Response
from ..protocol.http import HTTPRequest, HTTPResponse, asBytes
from ..model import Service, Application
from ..logging import logger
from typing import (
    Callable,
    Any,
    Coroutine,
    Union,
    Set,
    Optional,
    AsyncIterable,
    Awaitable,
    cast,
)
import types
import asyncio

# --
# ## ASGI Bridge
#
# Exposes Extra applications through the ASGI gateway.

logging = logger("asgi.bridge")

# SEE: https://asgi.readthedocs.io/en/latest/specs/main.html

TScope = dict[str, Any]
TSend = Callable[[dict[str, Any]], Coroutine]


async def streamBodyHelper(
    body: AsyncIterable[Union[bytes, str]],
    send: Callable[[dict[str, Any]], Awaitable[None]],
):
    """A helper function that will take a response body and stream it through
    the `send` function."""
    count = 0
    async for chunk in body:
        await send(
            {"type": "http.response.body", "body": asBytes(chunk), "more_body": True}
        )
        count += 1
    # We notify that it's the end of the body, and we send a 0-byte payload.
    await send({"type": "http.response.body", "body": b"", "more_body": False})


class ASGIBridge:
    """Manages the input and output through the ASGI interface. The `run`
    method will read from the ASGI and then feed data to the request(ie.
    more data is comming) or modify the state of the request(ie. client
    disconnected, server terminated)."""

    async def run(self, app: Application, scope: TScope, receive, send):
        """Runs a complete transaction, starting with the initiation of the
        transaction, the creation of the request, the handling of the request
        and the interpretation of any message coming on the ASGI channel."""

        async def http_request_reader(size: int = -1):
            """Reads from the ASGI feed. As the ASGI feed contains both request
            data and internal ASGI data, the readers needs to dispatch some of the
            messages to the bridge, and buffer the ones that have already been
            received."""
            raise NotImplementedError

        # We create a request and read from ASGI up until the request is initialized
        request = HTTPRequest.Create().init(http_request_reader)
        while not request.isInitialized:
            # If we get a False from ASGI, this means that the connection
            # as shutdown so we shutdown everything.
            # SEE:SHUTDOWN
            if await self.readFromASGI(app, request, scope, receive, send) == False:
                log("asgi.bridge", "Shutdown message received, canceling the request")
                request.recycle()
                return None

        # NOTE: That chunk should be pretty common across bridges
        # TODO: This is now Application.proces
        route, params = app.dispatcher.match(request.method, request.path)
        if route:
            handler = route.handler
            assert handler, f"Route has no handler defined: {route}"
            response = handler(request, params)
        else:
            response = app.onRouteNotFound(request)
        # We now process the response, we start by writing stuff, and then
        # we read for updates. Note that because the Request was created with
        # a reader, the reader_task will only read the ASGI messages not read
        # by the request.
        writer_task = asyncio.create_task(self.writeToASGI(app, response, scope, send))
        reader_task = asyncio.create_task(
            self.readFromASGI(app, request, scope, receive, send)
        )
        tasks: Set[asyncio.Future] = {reader_task, writer_task}
        is_running = True
        # This is the main loop where we're reacting to successful reads or
        # writes. In a normal situation, there should be only reads.
        while is_running:
            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )
            if reader_task in done:
                # We've got an update from the ASGI server
                asgi_message = cast(dict[str, str], reader_task.result())
                asgi_message_type = asgi_message["type"]
                if asgi_message_type == "http.disconnect":
                    # We cleanup any remaining tasks
                    for task in pending:
                        try:
                            task.cancel()
                            await task
                        except Exception as e:
                            logging.warning(
                                f"Task failed during cancellation: {task}, {e}"
                            )
                else:
                    logging.warning("Unsupported ASGI message", type=asgi_message_type)
            elif writer_task in done:
                result = writer_task.result()
            is_running = bool(len(pending))

    async def readFromASGI(
        self, app: Application, request: HTTPRequest, scope: TScope, receive, send
    ):
        """Reads from the ASGI server, dispatching the message by type to the
        corresponding methods."""
        # SEE: https://asgi.readthedocs.io/en/latest/specs/www.html
        message = await receive()
        protocol = scope["type"]
        if protocol == "http" or protocol == "https":
            return await self.onASGIHTTPMessage(app, request, scope, message, send)
        elif protocol == "lifespan":
            return await self.onASGILifespan(app, request, scope, message, send)
        else:
            logging.warning(f"Unsupported ASGI protocol: {protocol}")
            return None

    async def onASGIHTTPMessage(
        self, app: Application, request: HTTPRequest, scope: TScope, message, send
    ):
        """Handles an ASGI HTTP message."""
        # SEE: https://asgi.readthedocs.io/en/latest/specs/www.html
        if not request.isInitialized:
            protocol = scope["type"]
            # NOTE: Not sure how it stacks against scope["scheme"]
            # We copy the attributes here
            request.protocol = protocol
            request.version = scope["http_version"]
            request.method = scope["method"]
            request.path = scope["path"]
            request.query = scope["query_string"]
            # client: It's an Iterable[str,int]
            # server: It's an Iterable[str,int]
            for name, value in scope["headers"]:
                request.setHeader(name, value)
            request.open()
        if message["type"] == "http.disconnect":
            request.close()
        return message

    async def onASGILifespan(
        self, app: Application, request: HTTPRequest, scope: TScope, message, send
    ):
        """Handles an ASGI lifespan message."""
        # SEE: https://asgi.readthedocs.io/en/latest/specs/lifespan.html
        # It's not ideal to have it here
        if message["type"] == "lifespan.startup":
            await app.start()
            await send({"type": "lifespan.startup.complete"})
            return message
        elif message["type"] == "lifespan.shutdown":
            await app.stop()
            await send({"type": "lifespan.shutdown.complete"})
            # We notify of the end of the stream.
            # SEE:SHUTDOWN
            return False
        else:
            raise ValueError(f"Unsupported protocol: {protocol}")

    async def writeToASGI(
        self,
        app: Application,
        response: Union[Coroutine, Response],
        scope: TScope,
        send,
    ):
        # FROM: https://asgi.readthedocs.io/en/latest/specs/www.html
        # Servers are responsible for handling inbound and outbound chunked
        # transfer encodings. A request with a chunked encoded body should be
        # automatically de-chunked by the server and presented to the
        # application as plain body bytes; a response that is given to the
        # server with no Content-Length may be chunked as the server sees fit.
        # Sending the start
        if isinstance(response, Coroutine):
            response = await response
        assert isinstance(response, Response)
        headers = [_ for _ in response.headers.items()]
        try:
            await send(
                {
                    "type": "http.response.start",
                    "status": response.status,
                    "headers": headers,
                }
            )
        except asyncio.CancelledError:
            response.recycle()
            return None
        # Now we take care of the body
        if response.isEmpty:
            try:
                await send(
                    {
                        "type": "http.response.body",
                    }
                )
            except asyncio.CancelledError:
                pass
        else:
            bodies_left = len(response.bodies)
            count = 0
            for value, contentType in response.bodies:
                if isinstance(value, types.AsyncGeneratorType):
                    try:
                        await streamBodyHelper(value, send)
                    except asyncio.CancelledError:
                        break
                else:
                    try:
                        await send(
                            {
                                "type": "http.response.body",
                                "body": value,
                                "more_body": count < bodies_left - 1,
                            }
                        )
                    except asyncio.CancelledError:
                        break
        # We recycle the response
        response.recycle()


def server(*services: Union[Application, Service]) -> Callable:
    """Creates an ASGI bridge, mounts the services into an application
    and returns the ASGI application handler."""
    bridge = ASGIBridge()
    # This extracts and instanciates the services and applications that
    # are given here.
    services = [_() if isinstance(_, type) else _ for _ in services]
    app = [_ for _ in services if isinstance(_, Application)]
    services = [_ for _ in services if isinstance(_, Service)]
    app = cast(Application, app[0] if app else Application())
    # Now we mount all the services on the application
    for service in services:
        logging.info(f"Mounting service: {service}")
        app.mount(service)
    # Ands we're ready for the main loop

    async def application(scope: TScope, receive, send):
        """ASGI Application"""
        await bridge.run(app, scope, receive, send)

    return application


# EOF
