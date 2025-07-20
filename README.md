                      __                   ._.
      ____  ___  ____/  |_ _______ _____   | |
    _/ __ \ \  \/  /\   __\\_  __ \\__  \  | |
    \  ___/  >    <  |  |   |  | \/ / __ \_ \|
     \___  >/__/\_ \ |__|   |__|   (____  / __
         \/       \/                    \/  \/

Extra is an toolkit to write HTTP/1.1 web services and applications, with
first class support for streaming.

It is focused on providing primitives for creating web services,
implemented to work well both in development and production while
providing a great developer experience.

Key Features:

-   Client and server
-   Streaming reads and writes, lazy decoding and encoding
-   Embedded asynchronous HTTP/1 development server
-   Only requires Python stdlib
-   Good baseline performance (5-10K RPS on average hardware)

Design principles:

-   Declarative: decorators to expose methods as web services
-   Stream-oriented: encourages writing stream processing handlers
-   Service focused: template are left out, but lots of building blocks
    are available for services.

Highlights:

- Pre/post conditions for request handlers
- HTML templating (plays nice with HTMX)
- CORS support
- Configurable proxy support
- Integrated logging
- Regexp-based tree router

Extra is the successor of [Retro](https://github.com/sebastien/retro),
one of the oldest decorator-based framework for HTTP applications and
built on the 15+ years of experience developing and maintaining that
toolkit.

Like Retro, Extra is designed as a kit, providing easily composable
building blocks that help you build fast, readable and resilient web
services.

Similar projects include [Quart](https://github.com/pgjones/quart),
[Starlette](https://github.com/encode/starlette),
[bareASGI](https://github.com/rob-blackbourn/bareASGI) and of
course, [FastAPI](https://fastapi.tiangolo.com/).

# Example: Hello, World! Service

Here is `helloworld.py`:

``` python
from extra import Service, HTTPRequest, HTTPResponse, on, run

class HelloWorld(Service):
    @on(GET="{any}")
    def helloWorld(self, request: HTTPRequest, any:str) -> HTTPResponse:
        return request.respond(b"Hello, World !", "text/plain")

app = run(HelloWorld())
```

