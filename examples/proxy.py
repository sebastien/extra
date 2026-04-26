"""
Proxy with Header Manipulation Example

This demonstrates how to build a reverse proxy that forwards requests
to a backend server while manipulating headers along the way.
Features shown:
- Catch-all route to forward any request to a target
- Reading and filtering request headers
- Adding X-Forwarded-For / X-Forwarded-Host headers
- Stripping and rewriting response headers
- Using @pre/@post middleware for header manipulation
- Making outgoing HTTP requests with HTTPClient

Usage:
    python proxy.py
    python proxy.py https://httpbin.org

Test with:
    curl -v http://localhost:8000/get
    curl -v http://localhost:8000/headers
    curl -v -X POST -d '{"key":"value"}' -H "Content-Type: application/json" http://localhost:8000/post
    curl -v -H "X-Custom: hello" http://localhost:8000/headers
"""

from extra import Service, HTTPRequest, HTTPResponse, on, run
from extra.decorators import pre, post
from extra.client import HTTPClient
from extra.utils.uri import URI
from extra.utils.logging import info
import sys

# --
# Target server to proxy to (default: httpbin.org which echoes back
# request details, making it easy to verify header manipulation).
TARGET = URI.Parse(sys.argv[1] if len(sys.argv) > 1 else "https://httpbin.org")

# --
# Headers we never want to forward to the backend.
STRIPPED_REQUEST_HEADERS: set[str] = {
	"Host",
	"Connection",
	"Transfer-Encoding",
}

# --
# Headers we strip from the backend response before returning it.
STRIPPED_RESPONSE_HEADERS: set[str] = {
	"Connection",
	"Keep-Alive",
	"Transfer-Encoding",
}


# --
# Middleware: add forwarding headers to every incoming request.
@pre
def addForwardingHeaders(request: HTTPRequest) -> HTTPRequest:
	"""Injects X-Forwarded-* headers so the backend knows the original client."""
	request.setHeader("X-Forwarded-For", request.peer or "unknown")
	request.setHeader("X-Forwarded-Host", request.getHeader("Host") or "localhost")
	request.setHeader("X-Forwarded-Proto", "http")
	return request


# --
# Middleware: tag every response with a proxy identifier header.
@post
def addProxyHeaders(request: HTTPRequest, response: HTTPResponse) -> HTTPResponse:
	"""Adds an X-Proxy header and strips unwanted backend headers."""
	response.setHeader("X-Proxy", "extra-proxy-example")
	# Strip headers we don't want to pass back to the client
	for name in STRIPPED_RESPONSE_HEADERS:
		if name in response.headers.headers:
			del response.headers.headers[name]
	return response


class Proxy(Service):
	"""A simple reverse proxy that forwards all requests to a target server."""

	@on(
		GET="{path:any}",
		POST="{path:any}",
		PUT="{path:any}",
		DELETE="{path:any}",
		PATCH="{path:any}",
		HEAD="{path:any}",
	)
	@addForwardingHeaders
	@addProxyHeaders
	async def proxyRequest(self, request: HTTPRequest, path: str) -> HTTPResponse:
		"""Forward the request to the target, manipulating headers on the way."""
		# Load the full request body (if any)
		body: bytes | None = await request.body.load()

		# Build the outgoing headers: copy from the original request,
		# stripping what we don't want and overriding the Host.
		outgoing: dict[str, str] = {}
		for name, value in request.headers.items():
			if name not in STRIPPED_REQUEST_HEADERS:
				outgoing[name] = value
		outgoing["Host"] = TARGET.host or "localhost"

		req_path = f"{TARGET.path or ''}/{path}" if TARGET.path else f"/{path}"
		info(
			"Proxying",
			Method=request.method,
			Path=req_path,
			Target=f"{TARGET.host}",
		)

		# Forward the request to the target server
		res: HTTPResponse | None = None
		async for atom in HTTPClient.Request(
			host=TARGET.host or "localhost",
			path=req_path,
			method=request.method,
			body=body or None,
			headers=outgoing,
			ssl=TARGET.ssl or False,
			port=TARGET.port,
			timeout=10.0,
		):
			if isinstance(atom, HTTPResponse):
				res = atom

		if not res:
			return request.fail(f"No response from upstream: {TARGET.host}{req_path}")

		return res


if __name__ == "__main__":
	info("Starting proxy example", Target=str(TARGET))
	info("Test endpoints:")
	info("  curl -v http://localhost:8000/get")
	info("  curl -v http://localhost:8000/headers")
	info("  curl -v -X POST -d '{\"key\":\"value\"}' -H 'Content-Type: application/json' http://localhost:8000/post")
	run(Proxy())

# EOF
