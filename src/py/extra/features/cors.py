from collections.abc import Callable, Iterable
from typing import Any
from urllib.parse import urlparse

from ..decorators import pre
from ..http.model import HTTPRequest, HTTPResponse

# SEE: http://stackoverflow.com/questions/16386148/why-browser-do-not-follow-redirects-using-xmlhttprequest-and-cors/20854800#20854800


ANY = "*"


def _pick(
	value: Any,
	alias: Any,
	*,
	default: Any,
	name: str,
) -> Any:
	if value is not None and alias is not None:
		raise ValueError(f"Use either '{name}' or its alias, not both")
	if value is not None:
		return value
	if alias is not None:
		return alias
	return default


def _matchPart(pattern: str, value: str) -> bool:
	if pattern == ANY:
		return True
	if pattern.startswith(f"{ANY}."):
		suffix = pattern[1:]
		return value.endswith(suffix) and value != suffix[1:]
	return pattern == value


def matches(pattern: str, origin: str) -> bool:
	parsed_pattern = urlparse(pattern)
	parsed_origin = urlparse(origin)
	if not parsed_pattern.scheme or not parsed_pattern.hostname:
		return pattern == origin
	if not parsed_origin.scheme or not parsed_origin.hostname:
		return False
	if not _matchPart(parsed_pattern.scheme, parsed_origin.scheme):
		return False
	if not _matchPart(parsed_pattern.hostname, parsed_origin.hostname):
		return False
	pattern_port = parsed_pattern.netloc.rsplit(":", 1)[1] if ":" in parsed_pattern.netloc else None
	origin_port = parsed_origin.port
	if pattern_port == ANY:
		return True
	return (int(pattern_port) if pattern_port is not None else None) == origin_port


def origins(
	*,
	hosts: Iterable[str] | None = None,
	host: Iterable[str] | None = None,
	subdomains: Iterable[str | None] | None = None,
	subdomain: Iterable[str | None] | None = None,
	ports: Iterable[int | str | None] | None = None,
	port: Iterable[int | str | None] | None = None,
	schemes: Iterable[str] | None = None,
	scheme: Iterable[str] | None = None,
) -> tuple[str, ...]:
	hosts_iter = hosts if hosts is not None else host
	if hosts_iter is None:
		raise ValueError("Missing required argument: 'hosts' or 'host'")
	hosts = tuple(hosts_iter)
	subdomains_iter = subdomains if subdomains is not None else subdomain
	subdomains = tuple(subdomains_iter) if subdomains_iter is not None else (None,)
	ports_iter = ports if ports is not None else port
	ports = tuple(ports_iter) if ports_iter is not None else (None,)
	schemes_iter = schemes if schemes is not None else scheme
	schemes = tuple(schemes_iter) if schemes_iter is not None else ("http", "https")
	res: list[str] = []
	seen: set[str] = set()
	for host_name in hosts:
		for subdomain_name in subdomains:
			name = f"{ANY}.{host_name}" if subdomain_name == ANY else f"{subdomain_name}.{host_name}" if subdomain_name else host_name
			for scheme_name in schemes:
				for port_value in ports:
					value = f"{scheme_name}://{name}{f':{port_value}' if port_value is not None else ''}"
					if value not in seen:
						seen.add(value)
						res.append(value)
	return tuple(res)


def allow(
	origin: str | None,
	allowed: Iterable[str] | Callable[[str], str | None] | None = None,
) -> str | None:
	if not origin:
		return None
	if allowed is None:
		return origin
	if callable(allowed):
		return allowed(origin)
	return origin if any(matches(pattern, origin) for pattern in allowed) else None


def anyorigin(
	allowed: Iterable[str] | Callable[[str], str | None] | None = None,
) -> Callable[[HTTPRequest, dict[str, Any]], HTTPResponse | None]:
	@pre
	def transform(request: HTTPRequest, _params: dict[str, Any]) -> HTTPResponse | None:
		value = request.getHeader("Origin")
		request.origin = allow(value, allowed)
		if value and not request.origin:
			return request.fail({"error": "Origin not allowed"}, status=403)
		return None

	return transform


def origin(
	allowed: Iterable[str] | Callable[[str], str | None] | None = None,
) -> Callable[[HTTPRequest, dict[str, Any]], HTTPResponse | None]:
	@pre
	def transform(request: HTTPRequest, _params: dict[str, Any]) -> HTTPResponse | None:
		value = request.getHeader("Origin")
		request.origin = allow(value, allowed)
		if not value:
			return request.fail({"error": "Missing Origin header"}, status=400)
		if not request.origin:
			return request.fail({"error": "Origin not allowed"}, status=403)
		return None

	return transform


def cors(
	allowed: Iterable[str] | Callable[[str], str | None] | None = None,
	*,
	credentials: bool = False,
	methods: tuple[str, ...] | list[str] = ("GET", "POST", "OPTIONS"),
	headers: list[str] | tuple[str, ...] | None = None,
) -> Callable[[HTTPRequest, HTTPResponse], HTTPResponse]:
	def transform(request: HTTPRequest, response: HTTPResponse) -> HTTPResponse:
		origin = getattr(request, "origin", None) or allow(
			request.getHeader("Origin"), allowed
		)
		return setCORSHeaders(
			response,
			origin=origin,
			headers=list(headers) if headers else None,
			allowAll=allowed is None,
			allowCredentials=credentials,
			methods=tuple(methods),
		)

	return transform


def preflight() -> Callable[[HTTPRequest, HTTPResponse], HTTPResponse]:
	def transform(request: HTTPRequest, response: HTTPResponse) -> HTTPResponse:
		if request.method == "OPTIONS":
			if requested := request.getHeader("Access-Control-Request-Method"):
				response.setHeader("Access-Control-Allow-Methods", requested)
			if requested := request.getHeader("Access-Control-Request-Headers"):
				response.setHeader("Access-Control-Allow-Headers", requested)
		return response

	return transform


def setCORSHeaders(
	request: HTTPRequest | HTTPResponse,
	*,
	origin: str | None = None,
	headers: list[str] | None = None,
	allowAll: bool = False,
	allowCredentials: bool | None = None,
	methods: tuple[str, ...] | list[str] = (
		"GET",
		"POST",
		"OPTIONS",
		"HEAD",
		"INFO",
		"PUT",
		"DELETE",
		"UPDATE",
	),
) -> HTTPResponse:
	"""Takes the given request or response, and return (a response) with the CORS headers set properly.

	See <https://en.wikipedia.org/wiki/Cross-origin_resource_sharing>
	"""
	if isinstance(request, HTTPRequest):
		response: HTTPResponse = request.respond(status=200)
		origin = origin or request.getHeader("Origin")
	else:
		response = request
	allow_origin = origin if origin and not allowAll else "*"
	allow_credentials = (
		"true"
		if allowCredentials or (allowCredentials is None and allow_origin != "*")
		else "false"
	)
	# SEE: https://stackoverflow.com/questions/46288437/set-cookies-for-cross-origin-requests
	# SEE: https://remysharp.com/2011/04/21/getting-cors-working
	# If the request returns a 0 status code, it's likely because of CORS
	response.setHeaders(
		{
			"Access-Control-Allow-Origin": allow_origin,
			"Access-Control-Allow-Headers": ",".join(headers) if headers else "*",
			"Access-Control-Allow-Methods": ", ".join(methods),
			"Access-Control-Allow-Credentials": allow_credentials,
			"Vary": "Origin",
		}
	)
	return response


# EOF
