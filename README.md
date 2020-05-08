Extra is an asynchronous HTTP/1, HTTP/2 and WebSocket micro framework written
in Python and compatible with ASGI and WSGI.

It is focused on providing a toolkit for creating web services, and
implemented to work well both in development and production while providing a
great developer experience.

Features:

-   ASGI & WSGI support (gives HTTP/1, HTTP/2 and WebSocket)
-   Streaming reads and writes, lazy decoding and encoding
-   Embedded asynchronous HTTP/1 development server
-   Dynamically (re)loadable services

Design principles

-   Decorators to expose methods as web services
-   Back-end focused: template is left out.

Extra is the successor of [Retro](https://github.com/sebastien/retro), one of
the oldest decorator-based framework for HTTP applications and build on the
15+ years of experience developing and maintaing that toolkit. Similar projects include [Quart](https://github.com/pgjones/quart) and [Starlette](https://github.com/encode/starlette).
