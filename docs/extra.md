# Extra (`extra`)

## A standalone, simple and performant HTTP/1.1 toolkit for Python services

Extra is a service-oriented HTTP toolkit for building web APIs and applications
with Python stdlib only. It provides declarative routing decorators, streaming
request/response primitives, an async server runtime, and optional AWS Lambda
integration.

For request body loading details, see the `Streaming request bodies` and
`Loading and decoding request bodies` sections in this document.
For a deep reference guide, see [`docs/ref-extra.md`](./ref-extra.md).

### Core exports (`extra`):

- `Service`: Base class for service-oriented handlers.
- `HTTPRequest` / `HTTPResponse`: Request/response model and response factory API.
- `on(...)`: Route decorator binding HTTP methods to path templates.
- `expose(...)`: Route decorator that serializes returned values as JSON.
- `pre(transform)` / `post(transform)`: Handler transforms before/after execution.
- `run(*components, ...)`: Starts the built-in async HTTP server.

### Service and application model (`extra.model`):

- `Application(services?)`: Route dispatcher + service lifecycle container.
- `Service(name?, prefix?)`: Mountable service with route handlers and lifecycle hooks.
- `mount(*components)`: Builds an app and mounts provided services.
- `components(*components)`: Groups `Application` and `Service` values.

### HTTP server runtime (`extra.server`):

- `run(...)`: High-level server entrypoint.
- `ServerOptions(...)`: Runtime options (host, port, backlog, keepalive, polling, logs).
- Async socket backend with keep-alive and HTTP/1.1 pipelining support.

### Request/response helper API (on `HTTPRequest` via `ResponseFactory`):

- `respond(...)`: Generic response factory.
- `returns(value, ...)`: JSON response helper.
- `respondText(...)` / `respondHTML(...)`: Text/HTML helpers.
- `respondFile(...)`: Static file response with ETag, range, and encoding support.
- `error(...)`, `fail(...)`, `notFound(...)`, `notAuthorized(...)`, `redirect(...)`.

### Request API (`HTTPRequest`):

- `headers`, `header(name)`, `getHeader(name)`: Header access.
- `query`, `param(name, default?, processor?)`: Query parameter access.
- `cookies()`, `cookie(name)`: Cookie access.
- `body`: Lazy body accessor (`HTTPBodyIO`/`HTTPBodyBlob`), populated by `load()`.
- `read()`: Async chunk iterator for raw body streaming.
- `load(size?)`: Loads and decodes body (bytes, form values, files, JSON), optionally in chunks.
- `raw`, `data`, `files`: Convenience accessors after `load()`.
- `onClose(callback)`: Close callback registration.

### Response API (`HTTPResponse`):

- `HTTPResponse.Create(...)`: Low-level response constructor.
- `head()`: Serialized response head bytes.
- `setHeader(name, value)` / `setHeaders({...})`: Header mutation.
- `getHeader(name)`: Header lookup.
- `onClose(callback)`: Close callback registration.

### Routing and path templates (`extra.routing` + decorators)

- Path templates support `{name}` and `{name:type}`.
- Typed parameters are extracted and converted automatically.
- Built-in route types include `string`, `int`, `float`, `number`, `path`, `any`, `rest`, and more.
- `@on(GET=..., POST=...)` supports multi-method mapping.
- `@on(GET_POST="...")` splits method aliases by `_`.
- Route priority can be set with `@on(priority=...)` / `@expose(priority=...)`.

### Middleware-like transforms (`extra.decorators`):

- `@pre(transform)`: Registers request pre-processing transform(s).
- `@post(transform)`: Registers response post-processing transform(s).
- `@when(predicate, ...)`: Predicate metadata for conditional handler execution.
- `@expose(...)`: Same route binding behavior as `@on(...)`, plus JSON serialization intent metadata.

### Optional modules:

- `extra.client`: Async HTTP client with pooling (`request(...)`, `pooling(...)`, `HTTPClient`).
- `extra.handler`: AWS Lambda bridge (`handler(...)`, `awslambda(...)`, event/response conversion).
- `extra.features.cors`: CORS helpers (`cors`, `setCORSHeaders`).
- `extra.services.files.FileService`: Static file/directory service.
- `extra.services.proxy.ProxyService`: Reverse proxy service.

### Differences with full-stack frameworks

- Service-first design: routing and HTTP primitives first, templates optional.
- Stream-oriented processing: request/response body streaming is a first-class path.
- No dependency runtime: core built on Python stdlib.
- Explicit request/response model, with low-level control when needed.
- Includes both server and client primitives in one toolkit.

### Using

```python
from extra import Service, HTTPRequest, HTTPResponse, on, run


class Hello(Service):
	PREFIX = "api/"

	@on(GET="hello/{name:string}")
	def hello(self, request: HTTPRequest, name: str) -> HTTPResponse:
		return request.respond(f"Hello, {name}!", "text/plain")


run(Hello(), host="0.0.0.0", port=8000)
```

### JSON APIs with `@expose`

```python
from extra import Service, expose, run
import time


class API(Service):
	PREFIX = "api/"

	@expose(GET="time")
	def now(self):
		return {"timestamp": time.time()}


run(API())
```

### Streaming request bodies

```python
from extra import Service, HTTPRequest, HTTPResponse, on


class Upload(Service):
	@on(POST="upload")
	async def upload(self, request: HTTPRequest) -> HTTPResponse:
		total = 0
		while chunk := await request.read():
			total += len(chunk)
		return request.returns({"received": total})
```

### Loading and decoding request bodies

```python
from extra import Service, HTTPRequest, HTTPResponse, on


class Forms(Service):
	@on(POST="submit")
	async def submit(self, request: HTTPRequest) -> HTTPResponse:
		await request.load()
		return request.returns(
			{
				"data": request.data,
				"files": len(request.files),
				"raw_size": len(request.raw or b""),
			}
		)
```

Important body-loading behavior:

- `read()` and `load()` are mutually exclusive for one request body: once `read()` consumes bytes, `load()` cannot reconstruct them.
- Use `read()` for one-pass streaming pipelines.
- Use `load()` when you need parsed values/files or repeated body access.
- For large uploads, `load(size=...)` returns an iterator-like loader so you can track `request.progress` while loading incrementally.

### File responses with caching and range support

```python
from pathlib import Path
from extra import Service, HTTPRequest, HTTPResponse, on


class Assets(Service):
	@on(GET="assets/{path:any}")
	def asset(self, request: HTTPRequest, path: str) -> HTTPResponse:
		file_path = Path("public") / path
		return request.respondFile(
			file_path,
			acceptEncoding=request.header("Accept-Encoding"),
			ifNoneMatch=request.header("If-None-Match"),
			ifModifiedSince=request.header("If-Modified-Since"),
			ifRange=request.header("If-Range"),
			rangeHeader=request.header("Range"),
		)
```

### AWS Lambda integration (`extra.handler`)

```python
from extra import Service, on
from extra.handler import handler


class API(Service):
	@on(GET="hello")
	def hello(self, request):
		return request.returns({"ok": True})


aws_handler = handler(API())
```

### API

### The `extra` module:

- `Service`: Base class for declarative HTTP services.
- `HTTPRequest`: HTTP request model and response helper factory.
- `HTTPResponse`: HTTP response model.
- `on(priority=0, **methods)`: Binds HTTP methods and routes to handlers.
- `expose(priority=0, compress=False, contentType=None, raw=False, **methods)`: Route decorator for JSON-style exposed endpoints.
- `pre(transform)`: Registers a pre-processing transform for the handler.
- `post(transform)`: Registers a post-processing transform for the handler.
- `run(*components, host=..., port=..., ...)`: Runs mounted services with the built-in async server.

### `@on` / `@expose` route patterns:

- `"{name}"`: Captures with inferred pattern from `name` when available.
- `"{name:type}"`: Captures using explicit route type.
- Examples:
  - `@on(GET="users/{id:int}")`
  - `@on(GET_POST="session")`
  - `@expose(GET=("a", "b"))`

### Service lifecycle:

- `init(self)`: Synchronous initialization hook called in constructor.
- `start(self)`: Async startup hook called when app starts.
- `stop(self)`: Async shutdown hook called when app stops.
- `PREFIX`: Class-level default mount prefix.
