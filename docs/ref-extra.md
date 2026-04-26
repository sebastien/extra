# Extra Reference Guide

A standalone, simple and performant HTTP/1.1 toolkit for Python, designed for
building service-oriented APIs with streaming-first primitives.

## Overview

Extra is centered on a small set of concepts:

- `Service` classes expose routes through decorators.
- `HTTPRequest` is both the incoming request model and a response factory.
- `HTTPResponse` is explicit and low-level when you need control.
- `run(...)` starts a built-in async HTTP server with keep-alive and pipelining support.

Extra keeps things composable: routing, request/response handling, streaming,
files, proxying, and AWS Lambda integration live in focused modules.

For a compact overview of the API surface, see [`docs/extra.md`](./extra.md).

## Quick Start

```python
from extra import Service, HTTPRequest, HTTPResponse, on, run


class Hello(Service):
	@on(GET="hello/{name:string}")
	def hello(self, request: HTTPRequest, name: str) -> HTTPResponse:
		return request.respond(f"Hello, {name}!", "text/plain")


run(Hello())
```

## Core Concepts

### Services

`Service` is the unit of composition. You define handlers as methods and mount
services into an application.

```python
from extra import Service, expose


class API(Service):
	PREFIX = "api/"

	def init(self) -> None:
		self.count = 0

	@expose(GET="counter")
	def counter(self):
		return {"counter": self.count}
```

Important service lifecycle hooks:

- `init(self)`: Called at instance initialization time.
- `start(self)`: Async startup hook.
- `stop(self)`: Async shutdown hook.

### Routes and Path Templates

Routes are declared with `@on(...)` and `@expose(...)`.

```python
@on(GET="users/{id:int}")
def user(self, request, id: int):
	...

@on(GET_POST="sessions")
def sessions(self, request):
	...
```

Common built-in path types:

| Type | Meaning | Example match |
| ---- | ------- | ------------- |
| `string` | Any non-slash segment | `hello-world` |
| `int` | Signed integer | `-42` |
| `float` | Float-like number | `3.14` |
| `number` | Int or float | `10` / `2.5` |
| `path` | Path-like chunk (no `:`/`@`) | `assets/main.js` |
| `any` | Any content (including empty) | `` |
| `rest` | Any non-empty remainder | `a/b/c` |

### Application Mounting

You can let `run(...)` mount services for you, or build apps manually.

```python
from extra.model import Application

app = Application()
app.mount(API())
```

Lifecycle flow:

```
Service(s) -> Application.mount(...) -> app.start() -> request dispatch -> app.stop()
```

## Request and Response Model

### `HTTPRequest`

`HTTPRequest` gives you headers, query params, cookies, and lazy body access.

| Member | Purpose |
| ------ | ------- |
| `headers` | Header dictionary |
| `header(name)` / `getHeader(name)` | Header lookup |
| `param(name, default?, processor?)` | Query parameter lookup |
| `cookies()` / `cookie(name)` | Cookie access |
| `body` | Lazy request body handle |
| `read()` | Async raw body chunk reader |
| `load(size?)` | Load + decode body into bytes/data/files |
| `raw` / `data` / `files` | Convenience accessors after `load()` |
| `onClose(callback)` | Register request-close callback |

Body loading patterns:

```python
# Stream chunks
while chunk := await request.read():
	...

# Load and decode body once, then access helpers
await request.load()
payload = request.raw        # bytes
fields = request.data        # dict (form/json)
uploads = request.files      # list[extra.protocol.http.File]

# Incremental loading for very large bodies
while request.load(size=1_000_000):
	print(request.progress)
```

Important: do not mix `read()` and `load()` on the same request. `read()` consumes
the incoming stream directly; `load()` buffers/parses it for later access.

### Response Helpers (via `HTTPRequest`)

`HTTPRequest` inherits `ResponseFactory`, so handlers can return responses with
specialized helpers:

- `respond(...)`: Generic response constructor.
- `returns(value, ...)`: JSON response helper.
- `respondText(...)`: Text/bytes helper.
- `respondHTML(...)`: HTML helper.
- `respondFile(...)`: File response with ETag, `If-None-Match`, `If-Modified-Since`, `Range`, `If-Range`, and `Accept-Encoding` support.
- `error(...)`, `fail(...)`, `notFound(...)`, `notAuthorized(...)`, `redirect(...)`.

### `HTTPResponse`

`HTTPResponse` is explicit and mutable before write-out.

| Method | Purpose |
| ------ | ------- |
| `HTTPResponse.Create(...)` | Factory constructor |
| `head()` | Serialize status line + headers |
| `getHeader(name)` | Read header |
| `setHeader(name, value)` | Set/remove a header |
| `setHeaders({...})` | Batch header updates |
| `onClose(callback)` | Register response-close callback |

## Decorators

### `@on(priority=0, **methods)`

Binds one handler to one or more method/path combinations.

```python
@on(GET="users")
@on(POST="users")
def users(self, request):
	...
```

You can also provide multiple paths per method:

```python
@on(GET=("/", "index", "home"))
def index(self, request):
	...
```

### `@expose(...)`

Like `@on`, but the returned value is serialized as JSON by default.

```python
@expose(GET="status")
def status(self):
	return {"ok": True}
```

Useful options:

- `raw=True`: Return `request.respond(...)` instead of JSON serialization.
- `contentType=...`: Override response content type.
- `compress=...`: Expose metadata (reserved for compression flow).

### `@pre` and `@post`

Attach pre/post transforms to handler methods.

```python
from extra.decorators import pre, post


@pre
def check_auth(request, params):
	if request.header("Authorization") is None:
		return request.notAuthorized()


@post
def add_server_header(request, response):
	response.setHeader("X-Server", "extra")
	return response
```

Use on handlers:

```python
@on(GET="secure")
@check_auth
@add_server_header
def secure(self, request):
	return request.returns({"ok": True})
```

### `@when(...)`

Registers predicates as route metadata on a handler.

```python
from extra.decorators import when


@when(lambda request, params: request.header("X-Enabled") == "1")
@on(GET="flagged")
def flagged(self, request):
	return request.respond("ok")
```

Note: `@when` metadata is available through decorator annotations, but the
default `Handler` execution path does not currently enforce these predicates.

## Server Runtime

### `run(*components, ...)`

Starts the built-in async socket server.

```python
run(MyService(), host="0.0.0.0", port=8000, keepalive=3600)
```

Main options:

| Option | Description | Default |
| ------ | ----------- | ------- |
| `host` | Bind host | from config (`0.0.0.0`) |
| `port` | Bind port | from config (`8000`) |
| `backlog` | Listen backlog | `10000` |
| `timeout` | Request timeout | `10.0` |
| `polling` | Accept loop polling timeout | `1.0` |
| `logRequests` | Log each request event | `True` |
| `keepalive` | Connection keep-alive timeout | `3600` |

## API Reference

### Top-level `extra` exports

- `Service`
- `HTTPRequest`
- `HTTPResponse`
- `on`
- `expose`
- `pre`
- `post`
- `run`

### `extra.model`

- `Service(name=None, prefix=None)`
- `Application(services=None)`
- `components(*components)`
- `mount(*components)`

`Application` methods:

- `mount(service, prefix=None)`
- `unmount(service)`
- `process(request)`
- `start()` / `stop()` / `reload()`

### `extra.http.api.ResponseFactory`

- `respond(...)`
- `empty(...)`
- `error(...)`
- `notAuthorized(...)`
- `notFound(...)`
- `fail(...)`
- `redirect(...)`
- `returns(...)`
- `respondText(...)`
- `respondHTML(...)`
- `respondFile(...)`
- `respondError(...)`
- `respondEmpty(...)`

### `extra.routing`

- `Route`: Path template parser and matcher.
- `Handler`: Runtime wrapper around decorated service methods.
- `Dispatcher`: Fast route dispatcher (static dict fast-path + compiled regex for dynamic routes).
- `Route.AddPattern(name, regexp, parser)`: Register custom parameter type.

## Streaming Patterns

### Streaming responses with generators

```python
@on(GET="stream")
def stream(self, request):
	def gen():
		yield "["
		for i in range(3):
			if i:
				yield ","
			yield str(i)
		yield "]"
	return request.respond(gen(), contentType="application/json")
```

### Server-Sent Events (SSE)

```python
@on(GET="events")
def events(self, request):
	async def stream():
		yield "event: ping\n"
		yield "data: hello\n\n"
	return request.respond(stream(), contentType="text/event-stream")
```

## Optional Modules

### HTTP Client (`extra.client`)

Low-level async HTTP client with connection pooling.

```python
from extra.client import request
from extra.http.model import HTTPResponse


async for atom in request("GET", "example.com", "/", ssl=True):
	if isinstance(atom, HTTPResponse):
		print(atom.status)
```

Connection pooling helper:

```python
from extra.client import pooling, request


with pooling(idle=30):
	...
```

### AWS Lambda Bridge (`extra.handler`)

```python
from extra.handler import handler


aws_handler = handler(MyService())
```

Key helpers:

- `handler(*components)` -> `AWSLambdaHandler`
- `awslambda(fn)` -> wraps request handler into AWS Lambda entrypoint
- `event(...)` -> helper to build API Gateway-like test event payloads

### CORS (`extra.features.cors`)

```python
from extra.features.cors import cors


@cors
@on(GET="public")
def public(self, request):
	return request.respond("ok")
```

### File and Proxy Services

- `extra.services.files.FileService`: Static file serving, directory listing, conditional/range support via `respondFile`.
- `extra.services.proxy.ProxyService`: Reverse proxy service with header filtering, optional CORS injection, and streaming support.

## Common Patterns

### JSON API Endpoints

```python
@expose(GET="time")
def time(self):
	import time
	return {"timestamp": time.time()}
```

### Mixed Sync + Async Handlers

```python
@on(GET="sync")
def sync_handler(self, request):
	return request.respond("sync")


@on(GET="async")
async def async_handler(self, request):
	return request.respond("async")
```

### Prefixing Service Routes

```python
class Admin(Service):
	PREFIX = "admin/"

	@on(GET="health")
	def health(self, request):
		return request.returns({"ok": True})
```

Resulting route: `/admin/health`

## Best Practices

1. **Use `@expose` for JSON APIs** and `@on` for fully custom response flows.
2. **Prefer streaming for large payloads** instead of loading everything in memory.
3. **Use `request.respondFile(...)`** for HTTP-correct static file responses (ETag/Range/304 handling).
4. **Keep pre/post transforms focused** (auth, tracing, headers, validation).
5. **Model services as bounded domains** and mount them with prefixes for clean route namespaces.
6. **Use typed route parameters** (`{id:int}`, `{delay:float}`) for cleaner handlers.
7. **Return explicit HTTP errors** with `notFound`, `notAuthorized`, `fail`, or custom statuses as needed.
