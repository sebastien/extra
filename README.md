                      __                   ._.
      ____  ___  ____/  |_ _______ _____   | |
    _/ __ \ \  \/  /\   __\\_  __ \\__  \  | |
    \  ___/  >    <  |  |   |  | \/ / __ \_ \|
     \___  >/__/\_ \ |__|   |__|   (____  / __
         \/       \/                    \/  \/

Extra is an toolkit to write HTTP/1.1 web services and applications, with
first class support for streaming.

Extra works also well in serverless mode, thanks to its AWS Lambda handler.

Extra is focused on providing primitives for creating web services,
implemented to work well both in development and production while
providing a great developer experience.

Key Features:

-   Server *and* client, with full control over requests and responses
-   AWS Lambda/Serverless support
-   Streaming reads and writes, lazy decoding and encoding
-   Embedded asynchronous HTTP/1 development server
-   No dependency, only requires Python stdlib
-   Good baseline performance, competitive with FastAPI (5-10K RPS on average hardware)

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
#!/usr/bin/env uv run --with extra-http
from extra import Service, HTTPRequest, HTTPResponse, on, run

class HelloWorld(Service):
    @on(GET="{any}")
    def helloWorld(self, request: HTTPRequest, any:str) -> HTTPResponse:
        return request.respond(b"Hello, World !", "text/plain")

app = run(HelloWorld())
```

# More examples

-   `examples/api.py`: JSON API with routing, type conversion, and service lifecycle
-   `examples/awslambda.py`: AWS Lambda handler integration with streaming support
-   `examples/capture.py`: Request inspection with catch-all routes and body streaming
-   `examples/client.py`: HTTP client with connection pooling and keepalive
-   `examples/client-gzip.py`: HTTP client with GZip decompression
-   `examples/client-sse.py`: HTTP client consuming Server-Sent Events streams
-   `examples/cors.py`: CORS headers, pre-flight handling, and cross-origin requests
-   `examples/fileserver.py`: Static file serving with MIME type detection
-   `examples/htmx.py`: Interactive web apps with HTMX and server-side rendering
-   `examples/middleware.py`: Pre/post middleware decorators for request/response processing
-   `examples/proxy.py`: Reverse proxy with header manipulation and forwarding
-   `examples/sse.py`: Server-Sent Events streaming with async generators
-   `examples/upload.py`: File upload handling with HTML forms
-   `examples/watch.py`: Filesystem change streaming via SSE using CLI watchers
-   `examples/workers.py`: Background task processing with asyncio queues
