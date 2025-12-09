#!/usr/bin/env python3
from ..model import Service
from ..http.model import HTTPRequest, HTTPResponse, headername
from ..http.parser import iparseCookie, formatCookie
from ..decorators import on
from ..server import run
from ..client import HTTPClient
from ..features.cors import setCORSHeaders
from .files import FileService
from ..utils.uri import URI
from ..utils.logging import info
from typing import NamedTuple
import argparse
import os


# Service: proxy
#
# A proxy service that is tuned to work as CORS proxy, which is very
# useful when  building services.

PROXY_ALLOWED_REQUEST_HEADERS = {
	"User-Agent",
	"Cookie",
	"Content-Type",
	"Accept-Language",
	"Accept",
	"Priority",
}

PROXY_STRIPPED_RESPONSE_HEADERS: set[str] = {
	"Connection",
	"Keep-Alive",
	"Proxy-Authenticate",
	"Proxy-Authorization",
	"Trailers",
	"Transfer-Encoding",
	"Upgrade",
	"Host",
	"Master-Only",
	"Content-Security-Policy",
	"Strict-Transport-Policy",
	"X-Content-Security-Policy-Nonce",
	"X-Permitted-Cross-Domain-Policies",
	"X-Xss-Protection",
	"X-Content-Type-Options",
}


def parseHeaderList(
	headers: list[str] | None, initial: set[str] | None = None
) -> set[str]:
	"""Parses a list of headers into a set of header names."""
	res: set[str] = set(initial or [])
	for header in headers or []:
		for h in header.split(","):
			if h == "null":
				res = set()
			else:
				res.add(headername(h.strip()))
	return res


class ProxyTarget(NamedTuple):
	uri: URI
	keepalive: bool = False  # Tells if the connection should be kept alive
	streaming: bool = False  # Support streaming bodies (SSE)
	cors: bool = False  # Tells if the service should inject CORS headers
	timeout: float = 2.0  # Default backend response timeout


# TODO: Abstract headers pre-processing and post-processing
class ProxyService(Service):
	# Header stripping can be configured
	allowedRequestHeaders: set[str]
	strippedRequestHeaders: set[str]
	allowedResponseHeaders: set[str]
	strippedResponseHeaders: set[str]

	def __init__(
		self,
		target: ProxyTarget,
		*,
		prefix: str | None = None,
		allowedRequestHeaders: set[str] | None = PROXY_ALLOWED_REQUEST_HEADERS,
		strippedRequestHeaders: set[str] | None = None,
		allowedResponseHeaders: set[str] | None = None,
		strippedResponseHeaders: set[str] | None = PROXY_STRIPPED_RESPONSE_HEADERS,
	):
		super().__init__(prefix=prefix)
		self.target: ProxyTarget = target
		self.allowedRequestHeaders = allowedRequestHeaders or set()
		self.strippedRequestHeaders = strippedRequestHeaders or set()
		self.allowedResponseHeaders = allowedRequestHeaders or set()
		self.strippedResponseHeaders = strippedResponseHeaders or set()
		info(f"Proxy service {self.prefix or '/'} to {target.uri}")
		if self.allowedRequestHeaders:
			info(f"Allowed request headers: {','.join(self.allowedRequestHeaders)}")
		elif not self.strippedRequestHeaders:
			info("All request headers allowed")
		if self.strippedResponseHeaders:
			info(f"Stripped request headers: {','.join(self.strippedResponseHeaders)}")
		if self.allowedResponseHeaders:
			info(f"Allowed response headers: {','.join(self.allowedResponseHeaders)}")
		elif not self.strippedResponseHeaders:
			info("All response headers allowed")
		if self.strippedResponseHeaders:
			info(f"Stripped response headers: {','.join(self.strippedResponseHeaders)}")

	@on(
		GET="{path:any}",
		POST="{path:any}",
		PUT="{path:any}",
		DELETE="{path:any}",
		PATCH="{path:any}",
		HEAD="{path:any}",
		OPTIONS="{path:any}",
	)
	async def proxy(self, request: HTTPRequest, path: str) -> HTTPResponse:
		# Handle preflight OPTIONS requests
		if request.method == "OPTIONS":
			response = request.respond(status=200)
			return (
				setCORSHeaders(
					response,
					origin=request.getHeader("Origin"),
					headers=(
						request.getHeader("Access-Control-Request-Headers") or ""
					).split(","),
				)
				if self.target.cors
				else response
			)
		body: bytes | None = await request.body.load()
		headers: dict[str, str] = {}
		# NOTE: We whitelist the request headers that we're passing down to
		# the backend. In particular, we're limited by the nencodings we accept
		for name, value in request.headers.items():
			if self.strippedRequestHeaders and name in self.strippedRequestHeaders:
				continue
			if not self.allowedRequestHeaders or name in self.allowedRequestHeaders:
				headers[name] = value
		# We ensure the host is there
		uri: URI = self.target.uri
		headers["Host"] = uri.host or "localhost"
		# Now we do the request
		res: HTTPResponse | None = None
		req_path: str = f"{uri.path or ''}{path}" if self.prefix else path
		info(f"Proxying {request.method} {path} to {uri / req_path}")
		async for atom in HTTPClient.Request(
			host=uri.host or "localhost",
			path=req_path,
			method=request.method,
			body=body or None,
			timeout=self.target.timeout,
			streaming=self.target.streaming,
			keepalive=self.target.keepalive,
			ssl=uri.ssl or False,
			headers=headers,
		):
			if isinstance(atom, HTTPResponse):
				res = atom
		if not res:
			return request.fail(f"Did not get a response for: {uri / req_path}")
		else:
			# We stripped some headers from the response
			if self.allowedResponseHeaders:
				for name in set(res.headers.headers.keys()).difference(
					self.allowedResponseHeaders
				):
					del res.headers.headers[name]
			for name in self.strippedResponseHeaders:
				if name in res.headers.headers:
					del res.headers.headers[name]
			updated_headers: dict[str, str] = {}
			# SEE: https://stackoverflow.com/questions/46288437/set-cookies-for-cross-origin-requests
			for name, value in res.headers.headers.items():
				if name == "Set-Cookie":
					# We loosen the cookies so that they flow
					cookies = []
					for cookie in iparseCookie(value):
						if cookie.key in ("Secure", "HTTPOnly"):
							continue
						elif cookie.value == "Secure":
							cookies.append(cookie._replace(value="Lax"))
						else:
							cookies.append(cookie)
					updated_headers[name] = formatCookie(cookies)
			res.headers.headers.update(updated_headers)
			return (
				setCORSHeaders(res, origin=request.getHeader("Origin"))
				if self.target.cors
				else res
			)


def main(args: list[str]) -> None:
	# Create the parser
	parser = argparse.ArgumentParser(
		description="Retro[+proxy]",
		formatter_class=argparse.ArgumentDefaultsHelpFormatter,  # Shows default values in help
	)

	# Register the options
	parser.add_argument(
		"-p",
		"--port",
		action="store",
		dest="port",
		type=int,
		help="Specifies the port",
		default=int(os.environ.get("PORT", 8000)),
	)
	parser.add_argument(
		"-c",
		"--cors",
		action="store_true",
		dest="cors",
		help="Proxy as CORS",
	)
	parser.add_argument(
		"-f",
		"--files",
		action="store",
		dest="files",
		help="Server local files",
	)
	parser.add_argument(
		"-t",
		"--throttle",
		action="store",
		dest="throttling",
		type=int,  # Specify type for automatic conversion
		help="Throttles connection speed (in Kbytes/second)",
		default=0,
	)
	parser.add_argument(
		"-i",
		"--allow-request-headers",
		action="append",
		dest="allowedRequestHeaders",
		metavar="HEADER_NAME",
		help="Header name to include from the request (can be repeated)",
	)
	parser.add_argument(
		"-x",
		"--strip-request-header",
		action="append",
		metavar="HEADER_NAME",
		dest="strippedRequestHeaders",
		help="Header name to exclude from the request (can be repeated)",
	)
	parser.add_argument(
		"-I",
		"--allow-response-headers",
		action="append",
		dest="allowedResponseHeaders",
		metavar="HEADER_NAME",
		help="Header name to include from the response (can be repeated)",
	)
	parser.add_argument(
		"-X",
		"--strip-response-header",
		action="append",
		metavar="HEADER_NAME",
		dest="strippedResponseHeaders",
		help="Header name to exclude from the response (can be repeated)",
	)

	# Add positional argument for the URL
	parser.add_argument(
		"url",
		metavar="URL",  # Name for the argument in usage messages
		nargs="+",  # One or more URLs
		help="The URL(s) to proxy",
	)

	# Parse the options and arguments
	# If args is None, it defaults to sys.argv[1:]
	options = parser.parse_args(args=args)

	components: list[Service] = []
	stripped_request_headers = parseHeaderList(options.strippedRequestHeaders)
	allowed_request_headers = parseHeaderList(
		options.allowedRequestHeaders, PROXY_ALLOWED_REQUEST_HEADERS
	)
	stripped_response_headers = parseHeaderList(
		options.strippedResponseHeaders, PROXY_STRIPPED_RESPONSE_HEADERS
	)
	allowed_response_headers = parseHeaderList(options.allowedResponseHeaders)
	for url in options.url:
		lc = url.split("=", 1)
		prefix, target = (None, url) if len(lc) == 1 else lc
		uri = URI.Parse(target)
		if not uri.host:
			raise RuntimeError(f"URI has no host: {url}")
		components.append(
			ProxyService(
				ProxyTarget(
					uri=uri,
					cors=options.cors,
				),
				prefix=prefix,
				allowedRequestHeaders=allowed_request_headers,
				strippedRequestHeaders=stripped_request_headers,
				allowedResponseHeaders=allowed_response_headers,
				strippedResponseHeaders=stripped_response_headers,
			)
		)

	# TODO: If proxy services start with /, this is pointless.
	if options.files:
		components.append(FileService(options.files))

	return run(*components, port=options.port)


if __name__ == "__main__":
	import sys

	main(sys.argv[1:])
# EOF
