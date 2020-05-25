```
                  __                   ._.
  ____  ___  ____/  |_ _______ _____   | |
_/ __ \ \  \/  /\   __\\_  __ \\__  \  | |
\  ___/  >    <  |  |   |  | \/ / __ \_ \|
 \___  >/__/\_ \ |__|   |__|   (____  / __
     \/       \/                    \/  \/
```

Extra is an asynchronous HTTP/1, HTTP/2 and WebSocket microframework written
in Python and compatible with ASGI and WSGI.

It is focused on providing a toolkit for creating web services, and
implemented to work well both in development and production while providing a
great developer experience.

Features:

-   ASGI & WSGI support (gives HTTP/1, HTTP/2 and WebSocket)
-   Streaming reads and writes, lazy decoding and encoding
-   Embedded asynchronous HTTP/1 development server
-   Mount services on FUSE and query from the CLI
-   Building blocks for channels, pub/sub, topic tree.
-   Multi-threaded async (leverage all cores)
-   Dynamically (re)loadable services

Design principles

-   Declarative: Decorators to expose methods as web services
-   Service focused: template are left out, but lots of building blocks for
    services.

Extra is the successor of [Retro](https://github.com/sebastien/retro), one of
the oldest decorator-based framework for HTTP applications and built on the
15+ years of experience developing and maintaing that toolkit.

Extra is designed as a kit, providing easily composable building blocks that
help you build fast, readable and resilient web serivces.

Similar projects include [Quart](https://github.com/pgjones/quart) and [Starlette](https://github.com/encode/starlette).
