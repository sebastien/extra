"""Read-only WebDAV service built from Extra's routing and streaming primitives."""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import formatdate, parsedate_to_datetime
from inspect import isawaitable
from typing import Any, AsyncIterator, Callable
from urllib.parse import quote, unquote, urlparse
from xml.etree import ElementTree as ET  # nosec B405: guarded input parsing and response generation

from ...decorators import on
from ...http.model import HTTPRequest, HTTPResponse
from ...http.status import HTTP_STATUS
from ...model import Service
from ...utils.files import parseRange
from .model import (
	WebDAVBackend,
	WebDAVCapabilities,
	WebDAVConflict,
	WebDAVPreconditionFailed,
	WebDAVProperty,
	WebDAVResource,
	WebDAVUnsupported,
)

DAV = "DAV:"
ET.register_namespace("D", DAV)
ReadPolicy = Callable[[HTTPRequest, str, WebDAVResource], bool | Any]
WritePolicy = Callable[[HTTPRequest, str, WebDAVResource | None], bool | Any]


def _path(path: str) -> str | None:
	parts = [part for part in unquote(path).replace("\\", "/").split("/") if part]
	if any(part in (".", "..") or "\x00" in part for part in parts):
		return None
	return "/" + "/".join(parts) if parts else "/"


def _href(path: str, collection: bool) -> str:
	value = quote(path, safe="/%:@")
	return value + "/" if collection and value != "/" else value


def _httpdate(value: float | None) -> str | None:
	return formatdate(value, usegmt=True) if value is not None else None


class WebDAVService(Service):
	"""Expose a :class:`WebDAVBackend` as a read-only WebDAV collection."""

	def __init__(
		self,
		backend: WebDAVBackend,
		*,
		prefix: str | None = None,
		canRead: ReadPolicy | None = None,
		canWrite: WritePolicy | None = None,
		maxDepth: int = 64,
		maxResources: int = 10_000,
	) -> None:
		super().__init__(prefix=prefix)
		self.backend = backend
		self.canRead: ReadPolicy = canRead or (lambda request, path, resource: True)
		self.canWrite: WritePolicy = canWrite or (lambda request, path, resource: True)
		self.maxDepth = maxDepth
		self.maxResources = maxResources

	@property
	def capabilities(self) -> WebDAVCapabilities:
		return getattr(self.backend, "capabilities", WebDAVCapabilities())

	@property
	def allow(self) -> str:
		cap = self.capabilities
		methods = ["OPTIONS"]
		methods += [
			name
			for name, enabled in (
				("GET", cap.get),
				("HEAD", cap.head),
				("PROPFIND", cap.propfind),
			)
			if enabled
		]
		methods += [
			name
			for name, enabled in (
				("PUT", cap.put),
				("MKCOL", cap.mkcol),
				("DELETE", cap.delete),
				("COPY", cap.copy),
				("MOVE", cap.move),
				("PROPPATCH", cap.propertyWrite),
			)
			if enabled
		]
		return ", ".join(methods)

	async def _writeResource(
		self, request: HTTPRequest, path: str
	) -> tuple[str, WebDAVResource | None, HTTPResponse | None]:
		clean = _path(path)
		if clean is None or clean == "/":
			return "", None, request.error(409, "Invalid resource path")
		resource = await self.backend.stat(clean)
		allowed = self.canWrite(request, clean, resource)
		if isawaitable(allowed):
			allowed = await allowed
		if not allowed:
			return clean, resource, request.notAuthorized()
		if match := request.header("If-Match"):
			if resource is None or not self._matchesETag(match, resource.etag):
				return clean, resource, request.empty(status=412)
		if request.header("If-None-Match") == "*" and resource is not None:
			return clean, resource, request.empty(status=412)
		return clean, resource, None

	@staticmethod
	def _matchesETag(header: str, etag: str | None) -> bool:
		if header.strip() == "*":
			return True
		return etag is not None and any(
			item.strip() == etag for item in header.split(",")
		)

	def _unsupported(
		self, request: HTTPRequest, capability: bool
	) -> HTTPResponse | None:
		return None if capability else request.error(405, headers={"Allow": self.allow})

	@staticmethod
	def _destination(request: HTTPRequest) -> str | None:
		destination = request.header("Destination")
		if not destination:
			return None
		parsed = urlparse(destination)
		if parsed.netloc:
			try:
				destinationHost = parsed.hostname
				destinationPort = parsed.port
				host = urlparse("//" + (request.header("Host") or ""))
				requestHost = host.hostname
				requestPort = host.port
			except ValueError:
				return None
			if destinationHost is None or requestHost is None:
				return None
			if destinationHost.casefold() != requestHost.casefold():
				return None
			if destinationPort is not None and destinationPort != requestPort:
				return None
		return _path(parsed.path)

	async def start(self) -> None:
		start = getattr(self.backend, "start", None)
		if start:
			value = start()
			if isawaitable(value):
				await value

	async def stop(self) -> None:
		stop = getattr(self.backend, "stop", None)
		if stop:
			value = stop()
			if isawaitable(value):
				await value

	async def _resource(
		self, request: HTTPRequest, rawPath: str
	) -> WebDAVResource | None:
		path = _path(rawPath)
		if path is None:
			return None
		resource = await self.backend.stat(path)
		if resource is None:
			return None
		return resource if await self._allowed(request, path, resource) else None

	async def _allowed(
		self, request: HTTPRequest, path: str, resource: WebDAVResource
	) -> bool:
		allowed = self.canRead(request, path, resource)
		if isawaitable(allowed):
			allowed = await allowed
		return bool(allowed)

	def _headers(self, resource: WebDAVResource) -> dict[str, str]:
		headers: dict[str, str] = {}
		if self.capabilities.ranges:
			headers["Accept-Ranges"] = "bytes"
		if resource.etag:
			headers["Etag"] = resource.etag
		if modified := _httpdate(resource.modifiedAt):
			headers["Last-Modified"] = modified
		return headers

	@on(OPTIONS=("", "/", "/{path:any}"))
	def options(self, request: HTTPRequest, path: str = "") -> HTTPResponse:
		return request.empty(
			headers={
				"Allow": self.allow,
				"Dav": "1",
				"Ms-Author-Via": "DAV",
				**({"Accept-Ranges": "bytes"} if self.capabilities.ranges else {}),
			}
		)

	@on(GET_HEAD=("", "/", "/{path:any}"))
	async def read(self, request: HTTPRequest, path: str = "") -> HTTPResponse:
		resource = await self._resource(request, path)
		if resource is None:
			return request.notFound()
		if request.method == "GET" and not self.capabilities.get:
			return request.error(405, headers={"Allow": self.allow})
		if request.method == "HEAD" and not self.capabilities.head:
			return request.error(405, headers={"Allow": self.allow})
		if resource.collection:
			return request.error(405, headers={"Allow": self.allow})
		headers = self._headers(resource)
		if resource.etag and resource.etag in (request.header("If-None-Match") or ""):
			return request.empty(status=304, headers=headers)
		if resource.modifiedAt and (modified := request.header("If-Modified-Since")):
			try:
				if resource.modifiedAt <= parsedate_to_datetime(modified).timestamp():
					return request.empty(status=304, headers=headers)
			except (TypeError, ValueError, IndexError):
				pass
		start: int | None = None
		end: int | None = None
		status = 200
		if rangeHeader := request.header("Range"):
			if not self.capabilities.ranges:
				return request.error(416, headers=headers)
			if (
				resource.size is None
				or (parsed := parseRange(rangeHeader, resource.size)) is None
			):
				headers["Content-Range"] = f"bytes */{resource.size or 0}"
				return request.empty(status=416, headers=headers)
			start, end = parsed
			status = 206
			headers["Content-Range"] = f"bytes {start}-{end}/{resource.size}"
		length = (
			(end - start + 1)
			if start is not None and end is not None
			else resource.size
		)
		if request.method == "HEAD":
			return request.respond(
				None,
				status=status,
				contentType=resource.contentType or "application/octet-stream",
				contentLength=length,
				headers=headers,
			)
		content = await self.backend.open(resource.path, start, end)
		if not isinstance(content, bytes):
			streamSource = content

			async def stream() -> AsyncIterator[bytes]:
				async for chunk in streamSource:
					yield chunk

			content = stream()
		response = request.respond(
			content,
			status=status,
			contentType=resource.contentType or "application/octet-stream",
			contentLength=length,
			headers=headers,
		)
		return response

	@on(PUT="/{path:any}")
	async def put(self, request: HTTPRequest, path: str = "") -> HTTPResponse:
		if (response := self._unsupported(request, self.capabilities.put)) is not None:
			return response
		clean, previous, response = await self._writeResource(request, path)
		if response is not None:
			return response

		async def content() -> AsyncIterator[bytes]:
			async for chunk in request.read():
				if chunk:
					yield chunk

		try:
			resource = await self.backend.write(
				clean, content(), contentType=request.contentType
			)
		except WebDAVPreconditionFailed:
			return request.empty(status=412)
		except WebDAVConflict as error:
			return request.error(409, str(error))
		except WebDAVUnsupported:
			return request.error(501)
		return request.empty(
			status=204 if previous is not None else 201,
			headers=self._headers(resource),
		)

	@on(MKCOL="/{path:any}")
	async def makeCollection(
		self, request: HTTPRequest, path: str = ""
	) -> HTTPResponse:
		if (
			response := self._unsupported(request, self.capabilities.mkcol)
		) is not None:
			return response
		clean = _path(path)
		if clean is None or clean == "/":
			return request.error(409)
		if request.contentLength:
			return request.error(415)
		resource = await self.backend.stat(clean)
		if resource is not None:
			return request.error(405, headers={"Allow": self.allow})
		allowed = self.canWrite(request, clean, None)
		if isawaitable(allowed):
			allowed = await allowed
		if not allowed:
			return request.notAuthorized()
		try:
			created = await self.backend.makeCollection(clean)
		except WebDAVConflict as error:
			return request.error(409, str(error))
		except WebDAVUnsupported:
			return request.error(501)
		return request.empty(status=201, headers=self._headers(created))

	@on(DELETE="/{path:any}")
	async def remove(self, request: HTTPRequest, path: str = "") -> HTTPResponse:
		if (
			response := self._unsupported(request, self.capabilities.delete)
		) is not None:
			return response
		clean, resource, response = await self._writeResource(request, path)
		if response is not None:
			return response
		if resource is None:
			return request.notFound()
		try:
			await self.backend.delete(clean)
		except KeyError:
			return request.notFound()
		except WebDAVConflict as error:
			return request.error(409, str(error))
		except WebDAVUnsupported:
			return request.error(501)
		return request.empty(status=204)

	async def _copyOrMove(
		self, request: HTTPRequest, path: str, move: bool
	) -> HTTPResponse:
		capability = self.capabilities.move if move else self.capabilities.copy
		if (response := self._unsupported(request, capability)) is not None:
			return response
		source, resource, response = await self._writeResource(request, path)
		if response is not None:
			return response
		if resource is None:
			return request.notFound()
		destination = self._destination(request)
		if destination is None or destination == "/":
			return request.error(400, "Missing or invalid Destination")
		if destination == source or destination.startswith(source.rstrip("/") + "/"):
			return request.error(403, "Cannot copy a resource into itself")
		destinationResource = await self.backend.stat(destination)
		allowed = self.canWrite(request, destination, destinationResource)
		if isawaitable(allowed):
			allowed = await allowed
		if not allowed:
			return request.notAuthorized()
		overwrite = (request.header("Overwrite") or "T").upper() == "T"
		try:
			method = self.backend.move if move else self.backend.copy
			result = await method(source, destination, overwrite=overwrite)
		except WebDAVPreconditionFailed:
			return request.empty(status=412)
		except WebDAVConflict as error:
			return request.error(409, str(error))
		except KeyError:
			return request.notFound()
		except WebDAVUnsupported:
			return request.error(501)
		return request.empty(status=201, headers=self._headers(result))

	@on(COPY="/{path:any}")
	async def copy(self, request: HTTPRequest, path: str = "") -> HTTPResponse:
		return await self._copyOrMove(request, path, False)

	@on(MOVE="/{path:any}")
	async def move(self, request: HTTPRequest, path: str = "") -> HTTPResponse:
		return await self._copyOrMove(request, path, True)

	@on(PROPPATCH="/{path:any}")
	async def proppatch(self, request: HTTPRequest, path: str = "") -> HTTPResponse:
		if (
			response := self._unsupported(request, self.capabilities.propertyWrite)
		) is not None:
			return response
		clean = _path(path)
		if clean is None:
			return request.notFound()
		resource = await self.backend.stat(clean)
		if resource is None:
			return request.notFound()
		allowed = self.canWrite(request, clean, resource)
		if isawaitable(allowed):
			allowed = await allowed
		if not allowed:
			return request.notAuthorized()
		try:
			root = self._parseXML(await request.body.load() or b"")
			if root.tag != f"{{{DAV}}}propertyupdate":
				raise ValueError("Expected DAV:propertyupdate")
			changes: dict[str, Any] = {}
			for operation in root:
				if operation.tag not in (f"{{{DAV}}}set", f"{{{DAV}}}remove"):
					continue
				prop = next(iter(operation), None)
				if prop is None or prop.tag != f"{{{DAV}}}prop":
					continue
				for item in prop:
					changes[item.tag] = (
						None
						if operation.tag.endswith("remove")
						else WebDAVProperty(item.tag, item.text or "")
					)
			statuses = await self.backend.setProperties(clean, changes)
		except ValueError:
			return request.error(400, "Invalid PROPPATCH body")
		except WebDAVUnsupported:
			return request.error(501)
		responseRoot = ET.Element(f"{{{DAV}}}multistatus")
		responseElement = ET.SubElement(responseRoot, f"{{{DAV}}}response")
		ET.SubElement(responseElement, f"{{{DAV}}}href").text = self._resourceHref(
			resource
		)
		byStatus: dict[int, list[str]] = {}
		for name in changes:
			status = statuses.get(name, 500)
			byStatus.setdefault(status, []).append(name)
		for status, names in byStatus.items():
			propstat = ET.SubElement(responseElement, f"{{{DAV}}}propstat")
			prop = ET.SubElement(propstat, f"{{{DAV}}}prop")
			for name in names:
				ET.SubElement(prop, name)
			ET.SubElement(
				propstat, f"{{{DAV}}}status"
			).text = f"HTTP/1.1 {status} {HTTP_STATUS.get(status, 'Error')}"
		return request.respond(
			ET.tostring(responseRoot, encoding="utf-8", xml_declaration=True),
			status=207,
			contentType="application/xml; charset=utf-8",
		)

	def _parseXML(self, payload: bytes) -> ET.Element:
		if len(payload) > 65_536:
			raise ValueError("Invalid XML")
		try:
			# Restrict input to UTF-8 so declaration checks cannot be bypassed with
			# another XML encoding.
			text = payload.decode("utf-8-sig")
			if "<!" in text:
				raise ValueError("XML declarations are not allowed")
			return ET.fromstring(payload)  # nosec B314: guarded input parsing
		except (ET.ParseError, UnicodeDecodeError, ValueError) as error:
			raise ValueError("Invalid XML") from error

	def _requestedProperties(self, payload: bytes) -> tuple[str, set[str]]:
		if not payload:
			return "allprop", set()
		try:
			root = self._parseXML(payload)
		except ValueError as error:
			raise ValueError("Invalid PROPFIND XML") from error
		if root.tag != f"{{{DAV}}}propfind":
			raise ValueError("Expected DAV:propfind")
		for child in root:
			if child.tag == f"{{{DAV}}}allprop":
				return "allprop", set()
			if child.tag == f"{{{DAV}}}propname":
				return "propname", set()
			if child.tag == f"{{{DAV}}}prop":
				return "prop", {item.tag for item in child}
		raise ValueError("Expected allprop, propname, or prop")

	def _property(self, resource: WebDAVResource, name: str) -> ET.Element | None:
		key = name.split("}", 1)[-1]
		if name.startswith("{") and not name.startswith(f"{{{DAV}}}"):
			return None
		value = ET.Element(f"{{{DAV}}}{key}")
		if key == "resourcetype":
			if resource.collection:
				ET.SubElement(value, f"{{{DAV}}}collection")
		elif key == "getcontentlength" and resource.size is not None:
			value.text = str(resource.size)
		elif key == "getcontenttype" and resource.contentType:
			value.text = resource.contentType
		elif key == "getlastmodified" and (stamp := _httpdate(resource.modifiedAt)):
			value.text = stamp
		elif key == "creationdate" and resource.createdAt is not None:
			value.text = (
				datetime.fromtimestamp(resource.createdAt, timezone.utc)
				.isoformat()
				.replace("+00:00", "Z")
			)
		elif key == "getetag" and resource.etag:
			value.text = resource.etag
		elif key == "displayname":
			value.text = resource.name or "/"
		elif key == "supportedlock":
			pass
		else:
			return None
		return value

	def _backendProperty(self, property: WebDAVProperty) -> ET.Element:
		element = ET.Element(property.name)
		element.text = property.value
		for child in property.children:
			element.append(self._backendProperty(child))
		return element

	def _resourceHref(self, resource: WebDAVResource) -> str:
		base = "/" + self.prefix.strip("/") if self.prefix.strip("/") else ""
		path = base + ("" if resource.path == "/" else resource.path)
		return _href(path or "/", resource.collection)

	async def _responseElement(
		self, resource: WebDAVResource, mode: str, requested: set[str]
	) -> ET.Element:
		response = ET.Element(f"{{{DAV}}}response")
		ET.SubElement(response, f"{{{DAV}}}href").text = self._resourceHref(resource)
		live = {
			f"{{{DAV}}}{name}"
			for name in (
				"resourcetype",
				"getcontentlength",
				"getcontenttype",
				"getlastmodified",
				"creationdate",
				"getetag",
				"displayname",
				"supportedlock",
			)
		}
		backendProperties: dict[str, Any] = {}
		getProperties = getattr(self.backend, "getProperties", None)
		if self.capabilities.propertyRead and getProperties is not None:
			backendProperties = dict(await getProperties(resource.path, None))
		available = live | set(backendProperties)
		wanted = available if mode in ("allprop", "propname") else requested
		ok = ET.SubElement(response, f"{{{DAV}}}propstat")
		okProps = ET.SubElement(ok, f"{{{DAV}}}prop")
		missing: list[str] = []
		for name in sorted(wanted):
			value = self._property(resource, name)
			if value is None and (backendProperty := backendProperties.get(name)):
				value = self._backendProperty(backendProperty)
			if value is None:
				missing.append(name)
			elif mode == "propname":
				okProps.append(ET.Element(value.tag))
			else:
				okProps.append(value)
		ET.SubElement(ok, f"{{{DAV}}}status").text = "HTTP/1.1 200 OK"
		if missing:
			failed = ET.SubElement(response, f"{{{DAV}}}propstat")
			failedProps = ET.SubElement(failed, f"{{{DAV}}}prop")
			for name in missing:
				ET.SubElement(failedProps, name)
			ET.SubElement(failed, f"{{{DAV}}}status").text = "HTTP/1.1 404 Not Found"
		return response

	async def _walk(
		self,
		request: HTTPRequest,
		resource: WebDAVResource,
		depth: int,
		level: int = 0,
	) -> AsyncIterator[WebDAVResource]:
		yield resource
		if depth == 0 or not resource.collection:
			return
		if depth < 0 and level >= self.maxDepth:
			raise ValueError("Depth exceeds server limit")
		async for child in self.backend.iterChildren(resource.path):
			if not await self._allowed(request, child.path, child):
				continue
			async for item in self._walk(
				request, child, depth - 1 if depth > 0 else -1, level + 1
			):
				yield item

	@on(PROPFIND=("", "/", "/{path:any}"))
	async def propfind(self, request: HTTPRequest, path: str = "") -> HTTPResponse:
		resource = await self._resource(request, path)
		if resource is None:
			return request.notFound()
		try:
			mode, requested = self._requestedProperties(
				await request.body.load() or b""
			)
		except ValueError:
			return request.error(400, "Invalid PROPFIND body")
		depthHeader = (request.header("Depth") or "infinity").lower()
		if depthHeader == "0":
			depth = 0
		elif depthHeader == "1":
			depth = 1
		elif depthHeader == "infinity":
			depth = -1
		else:
			return request.error(400, "Invalid Depth header")
		root = ET.Element(f"{{{DAV}}}multistatus")
		count = 0
		try:
			async for item in self._walk(request, resource, depth):
				count += 1
				if count > self.maxResources:
					raise ValueError("Resource limit exceeded")
				root.append(await self._responseElement(item, mode, requested))
		except ValueError as error:
			return request.error(403, str(error), contentType="text/plain")
		return request.respond(
			ET.tostring(root, encoding="utf-8", xml_declaration=True),
			status=207,
			contentType="application/xml; charset=utf-8",
		)


# EOF
