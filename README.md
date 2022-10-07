                      __                   ._.
      ____  ___  ____/  |_ _______ _____   | |
    _/ __ \ \  \/  /\   __\\_  __ \\__  \  | |
    \  ___/  >    <  |  |   |  | \/ / __ \_ \|
     \___  >/__/\_ \ |__|   |__|   (____  / __
         \/       \/                    \/  \/

Extra is an asynchronous HTTP/1, HTTP/2 and WebSocket toolkit written in
Python and compatible with ASGI and WSGI.

It is focused on providing primitives for creating web services,
implemented to work well both in development and production while
providing a great developer experience.

Features:

-   Multiple backends: ASGI, WSGI, AsyncIO, AIOHTTP, AWS Lambda, socket, file
-   Streaming reads and writes, lazy decoding and encoding
-   Embedded asynchronous HTTP/1 development server
-   Mount services on FUSE and query from the CLI
-   Building blocks for channels, pub/sub, topic tree.
-   Multi-threaded async (leverage all cores)
-   Dynamically (re)loadable services
-   Implementation compiled using `mypyc` for performance

Design principles

-   Declarative: decorators to expose methods as web services
-   Stream-oriented: encourages writing stream processing handlers
-   Service focused: template are left out, but lots of building blocks
    are available for services.

Extra is the successor of [Retro](https://github.com/sebastien/retro),
one of the oldest decorator-based framework for HTTP applications and
built on the 15+ years of experience developing and maintainig that
toolkit.

Like Retro, Extra is designed as a kit, providing easily composable building blocks
that help you build fast, readable and resilient web services.

Similar projects include [Quart](https://github.com/pgjones/quart),
[Starlette](https://github.com/encode/starlette). and
[bareASGI](https://github.com/rob-blackbourn/bareASGI).

# Example: Hello, World! Service

Here is `helloworld.py`:

``` python
from extra import Service, Request, Response, on, server

class HelloWorld(Service):
    @on(GET="{any}")
    def helloWorld(self, request: Request) -> Response:
        return request.respond(b"Hello, World !"), b"text/plain")

app = server(HelloWorld)
```

And this above can be started with `uvicorn helloworld:app`.
