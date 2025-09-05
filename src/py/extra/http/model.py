import inspect
import os.path
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from functools import cached_property
from http.cookies import Morsel, SimpleCookie
from pathlib import Path
from tempfile import SpooledTemporaryFile
from typing import (
	Any,
	AsyncGenerator,
	Callable,
	Generator,
	Iterable,
	Literal,
	NamedTuple,
	TypeAlias,
	TypeVar,
	Union,
)

from ..utils.codec import BytesTransform
from ..utils.io import DEFAULT_ENCODING, asWritable
from ..utils.logging import warning
from ..utils.primitives import TPrimitive
from .api import ResponseFactory
from .status import HTTP_STATUS

# NOTE: MyPyC doesn't support async generators. We're trying without.

TControl = bool | None
T = TypeVar("T")

# -----------------------------------------------------------------------------
#
# HELPERS
#
# -----------------------------------------------------------------------------


def headername(name: str, *, headers: dict[str, str] = {}) -> str:
	"""Normalizes the header name as `Kebab-Case`."""
	if name in headers:
		return headers[name]
	key: str = name.lower()
	if key in headers:
		return headers[key]
	else:
		normalized: str = "-".join(_.capitalize() for _ in name.split("-"))
		headers[key] = normalized
		return normalized


# -----------------------------------------------------------------------------
#
# DATA MODEL
#
# -----------------------------------------------------------------------------


class TLSHandshake(NamedTuple):
	"""Represents a TLS handshake"""

	# Empty for now
	pass


class HTTPRequestLine(NamedTuple):
	"""Represents a request status line"""

	method: str
	path: str
	query: str
	protocol: str


class HTTPResponseLine(NamedTuple):
	"""Represents a response status line"""

	protocol: str
	status: int
	message: str


class HTTPHeaders(NamedTuple):
	"""Wraps HTTP headers, keeping key information for response/request processing."""

	headers: dict[str, str]
	contentType: str | None = None
	contentLength: int | None = None


class HTTPProcessingStatus(Enum):
	"""Internal parser/processor state management"""

	Processing = 0
	Body = 1
	Complete = 2
	Timeout = 10
	NoData = 11
	BadFormat = 12


# Type alias for the parser would produce
HTTPAtom: TypeAlias = Union[
	HTTPRequestLine,
	HTTPResponseLine,
	TLSHandshake,
	HTTPHeaders,
	HTTPProcessingStatus,
	"THTTPBody",
	"HTTPRequest",
	"HTTPResponse",
]

# -----------------------------------------------------------------------------
#
# ERRORS
#
# -----------------------------------------------------------------------------


class HTTPRequestError(Exception):
	"""To be raised by handlers to generate a 500 error."""

	def __init__(
		self,
		message: str,
		status: int | None = None,
		contentType: str | None = None,
		payload: TPrimitive | None = None,
	):
		super().__init__(message)
		self.message: str = message
		self.status: int | None = status
		self.contentType: str | None = contentType
		self.payload: TPrimitive | bytes | None = payload


# -----------------------------------------------------------------------------
#
# BODY
#
# -----------------------------------------------------------------------------


BODY_READER_TIMEOUT: float = 1.0


class HTTPBodyIO:
	__slots__ = ["reader", "read", "expected", "remaining", "existing"]
	"""Represents a body that is loaded from a reader IO."""

	def __init__(
		self,
		reader: "HTTPBodyReader",
		expected: int | None = None,
		existing: bytes | None = None,
	):
		self.reader: HTTPBodyReader = reader
		self.read: int = 0
		self.expected: int | None = expected
		self.remaining: int | None = expected
		self.existing: bytes | None = existing

	async def _read(
		self,
	) -> bytes | None:
		"""Reads the next available bytes"""
		if self.existing and self.read == 0:
			self.read += len(self.existing)
			return self.existing
		elif self.remaining:
			# FIXME: We should probably have a timeout there
			try:
				payload = await self.reader.load(size=self.remaining)
			except TimeoutError:
				warning(
					"Request body loading timed out",
					Remaining=self.remaining,
					Read=self.read,
				)
				return None
			if payload:
				n = len(payload)
				self.read += n
				self.remaining -= n
			return payload
		else:
			return None

	async def load(self) -> bytes:
		"""Fully loads the body."""
		res = bytearray()
		# FIXME: This would read other requests as well if there is no
		# remaining -- there should be at least a delimiter.
		while True:
			chunk = await self._read()
			if chunk:
				res += chunk
			else:
				return bytes(res)


class HTTPBodyBlob(NamedTuple):
	"""Represents a part (or a whole) body as bytes."""

	payload: bytes = b""
	length: int = 0
	# NOTE: We don't know how many is remaining
	remaining: int | None = None

	@staticmethod
	def FromBytes(data: bytes) -> "HTTPBodyBlob":
		return HTTPBodyBlob(payload=data, length=len(data))

	@property
	def raw(self) -> bytes:
		return self.payload

	async def load(
		self,
	) -> bytes | None:
		return self.payload


class HTTPBodyFile(NamedTuple):
	"""Represents an HTTP body from a file, potentially with a file descriptor."""

	path: Path
	fd: int | None = None

	@property
	def length(self) -> int:
		return self.path.stat().st_size


class HTTPBodyStream(NamedTuple):
	"""An HTTP body that is generated from a stream."""

	stream: Generator[str | bytes | TPrimitive, Any, Any]


class HTTPBodyAsyncStream(NamedTuple):
	"""An HTTP body that is generated from an asynchronous stream."""

	stream: AsyncGenerator[str | bytes | TPrimitive, Any]


# The different types of bodies that are managed
THTTPBody: TypeAlias = (
	HTTPBodyBlob | HTTPBodyFile | HTTPBodyStream | HTTPBodyAsyncStream
)


class HTTPBody:
	"""Contains helpers to work with bodies."""

	@staticmethod
	def HasRemaining(body: THTTPBody | None) -> bool:
		if body is None:
			return True
		elif isinstance(body, HTTPBodyBlob):
			return bool(body.remaining)
		elif isinstance(body, HTTPBodyStream) or isinstance(body, HTTPBodyAsyncStream):
			return True
		elif isinstance(body, HTTPBodyIO):
			return body.remaining is not None
		else:
			return False


# -----------------------------------------------------------------------------
#
# BODY TRANSFORMS
#
# -----------------------------------------------------------------------------
# We do separate the body, as typically the head of the request is there
# as a whole, and the body can be loaded through different loaders based
# on use case.


@dataclass(slots=True, frozen=True)
class StreamControl:
	"""Directives to be used to control a stream."""

	name: str


CLOSE_STREAM: StreamControl = StreamControl("close")


class HTTPBodyReader(ABC):
	"""A base class for being able to read a request body, typically from a
	socket."""

	__slots__ = ["transform"]

	def __init__(self, transform: BytesTransform | None = None) -> None:
		self.transform: BytesTransform | None = transform

	async def read(
		self, timeout: float = BODY_READER_TIMEOUT, size: int | None = None
	) -> bytes | None:
		chunk = await self._read(timeout=timeout, size=size)
		if chunk is not None and self.transform:
			res = self.transform.feed(chunk)
			return res if res else None
		else:
			return chunk

	@abstractmethod
	async def _read(
		self, timeout: float = BODY_READER_TIMEOUT, size: int | None = None
	) -> bytes | None:
		...

	# NOTE: This is a dangerous operation, as this way bloat the whole memory.
	# Instead, loading should spool the file.
	async def load(
		self, timeout: float = BODY_READER_TIMEOUT, size: int | None = None
	) -> bytes:
		"""Loads the entire body into a bytes array."""
		data = bytearray()
		# We may have an expected size to read
		left = size
		while True:
			chunk = await self.read(timeout=timeout, size=left)
			if not chunk:
				break
			else:
				data += chunk
			# If we had a size to read, then we update it
			if size is not None:
				left = size - len(chunk)
				if left <= 0:
					break
		return bytes(data)

	async def spool(
		self, timeout: float = BODY_READER_TIMEOUT
	) -> SpooledTemporaryFile[bytes]:
		"""The safer way to load a body especially if the file exceeds a given size."""
		with SpooledTemporaryFile(prefix="extra", suffix="raw") as f:
			while True:
				chunk = await self.read(timeout)
				if not chunk:
					break
				else:
					f.write(chunk)
			return f


class HTTPBodyWriter(ABC):
	"""A generic writer for bodies that supports bytes encoding and decoding."""

	__slots__ = ["transform", "shouldClose"]

	def __init__(self, transform: BytesTransform | None) -> None:
		self.transform: BytesTransform | None = transform
		self.shouldClose: bool = False

	async def write(self, body: THTTPBody | StreamControl | bytes | None) -> bool:
		"""Writes the given type of body."""
		if isinstance(body, bytes):
			return await self._writeBytes(body)
		elif isinstance(body, StreamControl):
			self.processControl(body)
			return True
		elif isinstance(body, HTTPBodyBlob):
			return await self._write(body.payload)
		elif isinstance(body, HTTPBodyFile):
			return await self._writeFile(body.path)
		elif isinstance(body, HTTPBodyStream):
			# No keep alive with streaming as these are long
			# lived requests.
			try:
				for _ in body.stream:
					if isinstance(_, StreamControl):
						self.processControl(_)
					else:
						await self._write(asWritable(_), True)
			finally:
				await self._write(b"", False)
			return True
		elif isinstance(body, HTTPBodyAsyncStream):
			# No keep alive with streaming as these are long
			# lived requests.
			try:
				async for _ in body.stream:
					if isinstance(_, StreamControl):
						self.processControl(_)
					else:
						await self._write(asWritable(_), True)
			finally:
				await self._write(b"", False)
			return True
		elif body is None:
			return True
		else:
			raise ValueError(f"Unsupported body format: {body}")

	async def flush(self) -> bool:
		if self.transform:
			chunk = self.transform.flush()
			if chunk:
				await self._writeBytes(chunk)
		return True

	def processControl(self, atom: StreamControl) -> None:
		if atom is CLOSE_STREAM:
			self.shouldClose = True

	async def _writeFile(self, path: Path, size: int = 64_000) -> bool:
		with open(path, "rb") as f:
			while chunk := f.read(size):
				await self._write(chunk, bool(chunk))
		return True

	async def _write(self, chunk: bytes, more: bool = False) -> bool:
		return await self._writeBytes(
			self.transform.feed(chunk, more) if self.transform else chunk, more
		)

	@abstractmethod
	async def _writeBytes(
		self, chunk: bytes | None | Literal[False], more: bool = False
	) -> bool:
		...


# -----------------------------------------------------------------------------
#
# REQUESTS
#
# -----------------------------------------------------------------------------


class HTTPRequest(ResponseFactory["HTTPResponse"]):
	"""Represents an HTTP requests, which also acts as a factory for
	responses."""

	__slots__ = [
		"protocol",
		"method",
		"path",
		"query",
		"_headers",
		"_body",
		"_reader",
		"_onClose",
	]

	def __init__(
		self,
		method: str,
		path: str,
		query: dict[str, str] | None,
		headers: HTTPHeaders,
		body: HTTPBodyIO | HTTPBodyBlob | None = None,
		protocol: str = "HTTP/1.1",
	):
		super().__init__()
		self.method: str = method
		self.path: str = path
		self.query: dict[str, str] | None = query
		self.protocol: str = protocol
		self._headers: HTTPHeaders = headers
		self._body: HTTPBodyIO | HTTPBodyBlob | None = body
		self._reader: HTTPBodyReader | None
		self._onClose: Callable[[HTTPRequest], None] | None = None

	@property
	def headers(self) -> dict[str, str]:
		return self._headers.headers

	@cached_property
	def _cookies(self) -> SimpleCookie:
		"""Returns the cookies (as a 'Cookie.SimpleCookie' instance)
		attached to this request."""
		cookies = SimpleCookie()
		h = self.header("Cookie")
		if h is not None:
			cookies.load(h)
		return cookies

	def cookies(self) -> Iterable[str]:
		for _ in self._cookies.keys():
			yield _

	def cookie(self, name: str) -> Morsel[str] | None:
		return self._cookies.get(name)

	# FIXME: Should be header
	def getHeader(self, name: str) -> str | None:
		return self.header(name)

	def header(self, name: str) -> str | None:
		return self._headers.headers.get(headername(name))

	def param(
		self,
		name: str,
		default: T | None = None,
		processor: Callable[[str | T | None], str | T | None] | None = None,
	) -> str | T | None:
		v = self.query.get(name, default) if self.query else default
		return processor(v) if processor else v

	@property
	def contentType(self) -> str | None:
		return self._headers.contentType

	@property
	def body(self) -> HTTPBodyIO | HTTPBodyBlob:
		if self._body is None:
			if not self._reader:
				raise RuntimeError("Request has no reader, can't read body")
			self._body = HTTPBodyIO(self._reader)
		elif isinstance(self._body, HTTPBodyBlob) and self._body.remaining:
			if not self._reader:
				raise RuntimeError("Request has no reader, can't read body")
			self._body = HTTPBodyIO(
				self._reader, expected=self._body.remaining, existing=self._body.payload
			)
		return self._body

	@property
	def contentLength(self) -> int | None:
		return self._headers.contentLength

	def onClose(
		self, callback: Callable[["HTTPRequest"], None] | None
	) -> "HTTPRequest":
		self._onClose = callback
		return self

	async def read(self) -> AsyncGenerator[bytes | None, None]:
		body = self.body
		if isinstance(body, HTTPBodyBlob):
			yield body.raw
			yield None
		else:
			while True:
				chunk = await body._read()
				yield chunk
				if chunk is None:
					break

	def respond(
		self,
		content: Any = None,
		contentType: str | None = None,
		contentLength: int | None = None,
		status: int = 200,
		headers: dict[str, str] | None = None,
		message: str | None = None,
	) -> "HTTPResponse":
		return HTTPResponse.Create(
			status=status,
			message=message,
			content=content,
			contentType=contentType,
			contentLength=contentLength,
			protocol=self.protocol,
			headers=headers,
		)

	# =========================================================================
	# API
	# =========================================================================

	def __str__(self) -> str:
		return f"Request({self.method} {self.path}{f'?{self.query}' if self.query else ''} {self.headers})"


# -----------------------------------------------------------------------------
#
# RESPONSE
#
# -----------------------------------------------------------------------------


class HTTPResponse:
	"""An HTTP response."""

	__slots__ = ["protocol", "status", "message", "headers", "body"]

	@staticmethod
	def Create(
		content: Any = None,
		contentType: str | None = None,
		contentLength: int | None = None,
		headers: dict[str, str] | None = None,
		status: int = 200,
		message: str | None = None,
		protocol: str = "HTTP/1.1",
	) -> "HTTPResponse":
		"""Factory method to create HTTP response objects."""
		payload: bytes | None = None
		updated_headers: dict[str, str] = {} if headers is None else {}
		should_close: bool = False

		# We process the body
		body: (
			HTTPBodyBlob | HTTPBodyFile | HTTPBodyStream | HTTPBodyAsyncStream | None
		) = None
		if content is None:
			pass
		elif isinstance(content, str):
			payload = content.encode(DEFAULT_ENCODING)
		elif isinstance(content, bytes):
			payload = content
		elif isinstance(content, Path):
			body = HTTPBodyFile(content.absolute())
			contentLength = os.path.getsize(body.path)
		elif inspect.isgenerator(content):
			body = HTTPBodyStream(content)
			# All streams should close the connection
			# TODO:In general, should close would be determined by the
			# presence of content length or not
			should_close = True
		elif inspect.isasyncgen(content):
			body = HTTPBodyAsyncStream(content)
			should_close = True
		else:
			raise ValueError(f"Unsupported content {type(content)}:{content}")
		# If we have a payload then it's a Blob response
		if payload is not None:
			contentLength = len(payload)
			body = HTTPBodyBlob(payload, contentLength)
		# Content Type
		content_type: str | None = headers.get("Content-Type") if headers else None
		if contentType is not None and contentType != content_type:
			updated_headers["Content-Type"] = contentType
			content_type = contentType
		# Content Length
		content_length_str: str | None = (
			headers.get("Content-Length") if headers else None
		)
		if (
			contentLength is not None
			and (t := str(contentLength)) != content_length_str
		):
			updated_headers["Content-Length"] = t
		elif contentLength is None:
			hcl: str | None = updated_headers.get("Content-Length") or (
				headers.get("Content-Length") if headers else None
			)
			if hcl is not None:
				contentLength = int(hcl)

		# TODO: We should have a response pipeline that can do things
		# like ETags, Ranged requests, etc.
		# We adjust any extra header
		# --
		# The response is ready to be packaged
		return HTTPResponse(
			status=status,
			message=message or HTTP_STATUS.get(status, "Unknown status"),
			headers=HTTPHeaders(
				(headers | updated_headers) if headers else updated_headers,
				contentType=contentType,
				contentLength=contentLength,
			),
			body=body,
			protocol=protocol,
			shouldClose=should_close if contentLength is None else False,
		)

	__slots__ = [
		"protocol",
		"status",
		"message",
		"headers",
		"body",
		"shouldClose",
		"_onClose",
	]

	def __init__(
		self,
		protocol: str,
		status: int,
		message: str | None,
		headers: HTTPHeaders,
		body: THTTPBody | None = None,
		shouldClose: bool = False,
	):
		super().__init__()
		self.protocol: str = protocol
		self.status: int = status
		self.message: str | None = message
		# NOTE: Content-Disposition headers may have a non-ascii value, but we
		# don't support that.
		self.headers: HTTPHeaders = headers
		self.body: THTTPBody | None = body
		self._onClose: Callable[[HTTPResponse], None] | None = None
		self.shouldClose: bool = shouldClose

	# TODO: Deprecate (in favour fo what?)
	def getHeader(self, name: str) -> str | None:
		return self.headers.headers.get(headername(name))

	def setHeader(self, name: str, value: str | int | None) -> "HTTPResponse":
		if value is None:
			del self.headers.headers[headername(name)]
		else:
			self.headers.headers[headername(name)] = str(value)
		return self

	def setHeaders(self, headers: dict[str, str | int | None]) -> "HTTPResponse":
		for k, v in headers.items():
			self.setHeader(k, v)
		return self

	def head(self) -> bytes:
		"""Serializes the head as a payload."""
		status: int = 204 if self.body is None else self.status
		message: str = self.message or HTTP_STATUS[status]
		lines: list[str] = [
			f"{headername(k)}: {v}" for k, v in self.headers.headers.items()
		]
		# TODO: No Content support?
		lines.insert(0, f"{self.protocol} {status} {message}")
		lines.append("")
		lines.append("")
		# TODO: UTF8 maybe? Why ASCII?
		return "\r\n".join(lines).encode("ascii")

	def onClose(
		self, callback: Callable[["HTTPResponse"], None] | None
	) -> "HTTPResponse":
		self._onClose = callback
		return self

	def __str__(self) -> str:
		return f"Response({self.protocol} {self.status} {self.message} {self.headers} {self.body})"


# EOF
