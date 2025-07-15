#!/usr/bin/env python3
from ..model import Service
from ..http.model import HTTPRequest, HTTPResponse
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


class ProxyTarget(NamedTuple):
	uri: URI
	keepalive: bool = False  # Tells if the connection should be kept alive
	streaming: bool = False  # Support streaming bodies (SSE)
	cors: bool = False  # Tells if the service should inject CORS headers
	timeout: float = 2.0  # Default backend response timeout


class ProxyService(Service):
	def __init__(self, target: ProxyTarget, *, prefix: str | None = None):
		super().__init__(prefix=prefix)
		self.target: ProxyTarget = target
		info(f"Proxy service {self.prefix or ""} to {target.uri}")

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
			if name in PROXY_ALLOWED_REQUEST_HEADERS:
				headers[name] = value
		# We ensure the host is there
		uri: URI = self.target.uri
		headers["Host"] = uri.host or "localhost"
		# Now we do the request
		res: HTTPResponse | None = None
		req_path: str = f"{uri.path or ""}{path}" if self.prefix else path
		info(f"Proxying {path} to {self.target.uri}")
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
			# TODO: We should have a postProcessHeaders method
			# We stripped some headers from the response
			for name in PROXY_STRIPPED_RESPONSE_HEADERS:
				if name in res.headers.headers:
					del res.headers.headers[name]
			updated_headers: dict[str, str] = {}
			# SEE: https://stackoverflow.com/questions/46288437/set-cookies-for-cross-origin-requests
			# for name, value in res.headers.headers.items():
			# 	match name:
			# 		# We loosen the cookies
			# 		case "Set-Cookie":
			# 			# FIXME: This is super brittle
			# 			updated_headers[name] = (
			# 				value.replace("Secure; ", "")
			# 				.replace("SameSite=Strict; ", "SameSite=Lax; ")
			# 				.replace("HTTPOnly", "")
			# 			).strip(";")
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

	# The positional arguments are now in options.url
	# No need for len(args) == 0 check as nargs='+' handles it by raising an error
	# if no URL is provided.
	# If you want to handle it gracefully without exiting, you might need a try-except
	# around parse_args or check options.url after parsing.
	# For now, we assume argparse's default error handling is sufficient.

	components: list[Service] = []
	for url in options.url:
		lc = url.split("=", 1)
		prefix, target = (None, url) if len(lc) == 1 else lc
		uri = URI.Parse(target)
		print(uri.asDict())
		if not uri.host:
			raise RuntimeError(f"URI has no host: {url}")
		components.append(
			ProxyService(
				ProxyTarget(
					uri=uri,
					cors=options.cors,
				),
				prefix=prefix,
			)
		)

	if options.files:
		components.append(FileService(options.files))
	return run(*components)


if __name__ == "__main__":
	import sys

	main(sys.argv[1:])
# EOF
