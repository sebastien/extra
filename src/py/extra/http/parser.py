from typing import Iterator, Iterable, ClassVar, Literal, NamedTuple, Union
from ..utils.io import LineParser, EOL
from .model import (
	HTTPRequest,
	HTTPResponse,
	HTTPRequestLine,
	HTTPResponseLine,
	HTTPHeaders,
	HTTPBodyBlob,
	HTTPAtom,
	HTTPProcessingStatus,
	TLSHandshake,
	headername,
)

# Readable buffer types accepted by feed() (server may pass memoryview).
TChunk = Union[bytes, bytearray, memoryview]

# Shared empty query for requests without '?'; callers must not mutate.
EmptyQuery: dict[str, str] = {}
# Shared empty body for no-body requests (GET/HEAD/…); do not mutate.
_EMPTY_BODY: HTTPBodyBlob = HTTPBodyBlob(b"", 0)

# Common header names — avoid headername() capitalize path on hot requests.
_COMMON_HEADERS: dict[str, str] = {
	"host": "Host",
	"connection": "Connection",
	"content-length": "Content-Length",
	"content-type": "Content-Type",
	"accept": "Accept",
	"accept-encoding": "Accept-Encoding",
	"user-agent": "User-Agent",
	"transfer-encoding": "Transfer-Encoding",
}


class MessageParser:
	"""Parses an HTTP request or response line."""

	__slots__ = ["line", "value", "skipping"]

	def __init__(self) -> None:
		self.line: LineParser = LineParser()
		self.value: HTTPRequestLine | HTTPResponseLine | TLSHandshake | None = None
		self.skipping: int = 0

	def flush(self) -> "HTTPRequestLine|HTTPResponseLine|TLSHandshake|None":
		res = self.value
		self.reset()
		return res

	def reset(self) -> "MessageParser":
		self.line.reset()
		self.value = None
		self.skipping = 0
		return self

	def feed(
		self, chunk: TChunk, start: int = 0
	) -> tuple[bool | None, int]:
		n = len(chunk)
		available = n - start
		# FIXME: In the future, we may want to do something with the TLS
		# handshake. This is something you can trigger with Firefox.
		if self.skipping:
			# We have reamining data to read/skip, so we do that
			read = min(available, self.skipping)
			self.skipping -= read
			return None, read
		elif (n - start) >= 5 and chunk[start] == 0x16:
			# This is a TLS Handshake, we parse the length
			size = 5 + (chunk[start + 3] << 8) + chunk[start + 4]
			if available >= size:
				return None, size
			else:
				self.skipping = size - available
				return None, available
		else:
			line, read = self.line.feed(chunk, start)
			if line:
				# Parse from bytes to avoid an intermediate full-line str when possible
				if len(line) >= 5 and line.startswith(b"HTTP/"):
					ln = line.decode("ascii")
					protocol, status, message = ln.split(" ", 2)
					self.value = HTTPResponseLine(
						protocol,
						int(status),
						message,
					)
				else:
					i = line.find(b" ")
					j = line.rfind(b" ")
					if i == -1 or j == -1 or j <= i:
						ln = line.decode("ascii")
						i = ln.find(" ")
						j = ln.rfind(" ")
						rest = ln[i + 1 : j]
						q = rest.find("?")
						self.value = HTTPRequestLine(
							ln[0:i],
							rest if q == -1 else rest[:q],
							"" if q == -1 else rest[q + 1 :],
							ln[j + 1 :],
						)
					else:
						target = line[i + 1 : j]
						q = target.find(b"?")
						if q == -1:
							path_b, query_b = target, b""
						else:
							path_b, query_b = target[:q], target[q + 1 :]
						self.value = HTTPRequestLine(
							line[:i].decode("ascii"),
							path_b.decode("ascii"),
							query_b.decode("ascii") if query_b else "",
							line[j + 1 :].decode("ascii"),
						)
				return True, read
			else:
				return None, read

	def __str__(self) -> str:
		return f"MessageParser({self.value})"


class HeadersParser:
	__slots__ = ["previous", "headers", "contentType", "contentLength", "line"]

	def __init__(self) -> None:
		super().__init__()
		self.line: LineParser = LineParser()
		self.headers: dict[str, str] = {}
		self.contentType: str | None = None
		self.contentLength: int | None = None
		# TODO: Close header
		# self.close:bool = False

	def flush(self) -> "HTTPHeaders|None":
		res = HTTPHeaders(self.headers, self.contentType, self.contentLength)
		self.reset()
		return res

	def reset(self) -> "HeadersParser":
		self.line.reset()
		self.headers = {}
		self.contentType = None
		self.contentLength = None
		return self

	def feed(
		self, chunk: TChunk, start: int = 0
	) -> tuple[str | Literal[False] | None, int]:
		"""Feeds data from chunk, starting at `start` offset. Returns
		a value and the next start offset. When the value is `None`, no
		header has been extracted, when the value is `False` it's an empty
		line, and when the value is `True`, a header was added."""
		chunks, read = self.line.feed(chunk, start)
		if chunks is None:
			return None, read
		elif chunks:
			line: bytes | None = self.line.flush()
			if line is None:
				return False, read
			# Headers are expected to be in ASCII format
			ln: str = line.decode("ascii")
			i = ln.find(":")
			if i != -1:
				# TODO: We should probably normalize the header there
				h = ln[:i].lower().strip()
				v = ln[i + 1 :].strip()
				if h == "content-length":
					try:
						self.contentLength = int(v)
					except ValueError:
						self.contentLength = None
				elif h == "content-type":
					self.contentType = v
				n: str = _COMMON_HEADERS.get(h) or headername(h)
				self.headers[n] = v
				# We have parsed a full header, we return True
				return n, read
			else:
				return None, read
		else:
			# An empty line denotes the end of headers
			return False, read

	def __str__(self) -> str:
		return f"HeadersParser({self.headers})"


class BodyEOSParser:
	"""Looks for an End-Of-Strem (EOS) delimiter in the body."""

	__slots__ = ["line", "data"]

	def __init__(self) -> None:
		self.line = LineParser()
		self.data: bytes | None = None

	def flush(self) -> HTTPBodyBlob:
		# TODO: We should check it's expected
		res = (
			HTTPBodyBlob(
				self.data,
				len(self.data),
			)
			if self.data is not None
			else HTTPBodyBlob()
		)
		self.reset()
		return res

	def reset(self, eos: bytes = EOL) -> "BodyEOSParser":
		self.line.reset(eos)
		self.data = None
		return self

	def feed(self, chunk: TChunk, start: int = 0) -> tuple[bytes | None, int]:
		line, read = self.line.feed(chunk, start)
		if line is None:
			return None, read
		else:
			data = self.line.flush()
			return data, read


class BodyRestParser:
	"""Consumes everything that is given to it."""

	__slots__ = ["buffer"]

	def __init__(self) -> None:
		self.buffer: bytearray = bytearray()

	def flush(self) -> HTTPBodyBlob:
		# TODO: We should check it's expected
		res: HTTPBodyBlob = HTTPBodyBlob(
			bytes(self.buffer[:]),
			len(self.buffer),
		)
		self.reset()
		return res

	def reset(self) -> "BodyRestParser":
		self.buffer.clear()
		return self

	def feed(self, chunk: TChunk, start: int = 0) -> tuple[bool | None, int]:
		self.buffer += chunk[start:]
		# We read everything and put it in the bugger
		return True, len(chunk) - start


class BodyLengthParser:
	"""Parses the body of a request with ContentLength set"""

	__slots__ = ["expected", "read", "data"]

	def __init__(self) -> None:
		self.expected: int | None = None
		self.read: int = 0
		self.data: bytearray = bytearray()

	def flush(self) -> HTTPBodyBlob:
		# TODO: We should check it's expected
		res = HTTPBodyBlob(
			bytes(self.data),
			self.read,
			0 if self.expected is None else self.expected - self.read,
		)
		self.reset()
		return res

	def reset(self, length: int | None = None) -> "BodyLengthParser":
		self.expected = length
		self.read = 0
		self.data.clear()
		return self

	def feed(self, chunk: TChunk, start: int = 0) -> tuple[bool, int]:
		size: int = len(chunk)
		left: int = size - start
		to_read: int = min(
			left, left if self.expected is None else self.expected - self.read
		)
		# FIXME: Is this correct?
		if to_read < left:
			self.data.extend(chunk[start : start + to_read])
			self.read += to_read
			return False, to_read
		else:
			self.data.extend(chunk[start:] if start else chunk)
			self.read += to_read
			return True, to_read


class HTTPParser:
	"""A stateful HTTP parser."""

	METHOD_HAS_BODY: ClassVar[set[str]] = {"POST", "PUT", "PATCH"}

	def __init__(self, *, requestsOnly: bool = False) -> None:
		self.message: MessageParser = MessageParser()
		self.headers: HeadersParser = HeadersParser()
		# FIXME: Not sure we need body EOS parser anymore.
		self.bodyEOS: BodyEOSParser = BodyEOSParser()
		self.bodyLength: BodyLengthParser = BodyLengthParser()
		self.bodyRest: BodyRestParser = BodyRestParser()
		self.parser: (
			MessageParser
			| HeadersParser
			| BodyEOSParser
			| BodyLengthParser
			| BodyRestParser
		) = self.message
		self.requestLine: HTTPRequestLine | HTTPResponseLine | TLSHandshake | None = (
			None
		)
		self.requestHeaders: HTTPHeaders | None = None
		# When True, skip yielding HTTPRequestLine/HTTPHeaders (server hot path).
		self.requestsOnly: bool = requestsOnly

	def _tryFastRequest(
		self, chunk: bytes, offset: int
	) -> tuple[HTTPRequest | None, int]:
		"""Fast path: one complete no-body request starting at offset.

		Returns (request, next_offset) or (None, offset) to fall back.
		Single ascii decode of the head block — much cheaper than the
		state-machine parser for keep-alive GETs that arrive in one read.
		"""
		if self.parser is not self.message:
			return None, offset
		# Reject TLS ClientHello
		if offset < len(chunk) and chunk[offset] == 0x16:
			return None, offset
		end = chunk.find(b"\r\n\r\n", offset)
		if end == -1:
			return None, offset
		# One decode for the entire request head
		try:
			text = chunk[offset:end].decode("ascii")
		except UnicodeDecodeError:
			return None, offset
		lines = text.split("\r\n")
		if not lines:
			return None, offset
		line0 = lines[0]
		sp1 = line0.find(" ")
		sp2 = line0.rfind(" ")
		if sp1 == -1 or sp2 <= sp1:
			return None, offset
		method = line0[:sp1]
		# Methods with bodies need Content-Length framing → slow path
		if method in self.METHOD_HAS_BODY:
			return None, offset
		target = line0[sp1 + 1 : sp2]
		protocol = line0[sp2 + 1 :]
		q = target.find("?")
		if q == -1:
			path = target
			query: dict[str, str] = EmptyQuery
		else:
			path = target[:q]
			query = parseQuery(target[q + 1 :])
		headers_map: dict[str, str] = {}
		content_type: str | None = None
		content_length: int | None = None
		for i in range(1, len(lines)):
			line = lines[i]
			if not line:
				continue
			colon = line.find(":")
			if colon == -1:
				continue
			h = line[:colon].lower().strip()
			v = line[colon + 1 :].strip()
			if h == "content-length":
				try:
					content_length = int(v)
				except ValueError:
					content_length = None
				if content_length:
					# Body bytes follow — slow path owns framing
					return None, offset
			elif h == "content-type":
				content_type = v
			# Prefer the common-header table; fall back to headername()
			name = _COMMON_HEADERS.get(h)
			headers_map[name if name is not None else headername(h)] = v
		req = HTTPRequest(
			method=method,
			path=path,
			query=query,
			headers=HTTPHeaders(headers_map, content_type, content_length),
			protocol=protocol,
			body=_EMPTY_BODY,
		)
		self.requestLine = None
		self.requestHeaders = None
		self.parser = self.message
		return req, end + 4

	def feed(self, chunk: TChunk) -> Iterator[HTTPAtom]:
		# FIXME: Should write to a buffer
		# Ensure we work with bytes for find/slice hot path
		if not isinstance(chunk, bytes):
			chunk = bytes(chunk)
		size: int = len(chunk)
		offset: int = 0
		# Fast path: complete no-body requests (Hello World / static GETs)
		if self.requestsOnly and self.parser is self.message:
			while offset < size:
				req, next_off = self._tryFastRequest(chunk, offset)
				if req is None:
					break
				yield req
				offset = next_off
			if offset >= size:
				return
		while offset < size:
			# The expectation here is that when we feed a chunk and it's
			# partially read, we don't need to re-feed it again. The underlying
			# parser will keep a buffer up until it is flushed.
			ln, read = self.parser.feed(chunk, offset)
			if ln is None:
				# NOTE: Keeping for reference here that we
				offset += read
			else:
				if self.parser is self.message:
					# We've parsed a request line
					line = self.message.flush()
					self.requestLine = line
					self.requestHeaders = None
					if line is not None:
						if not self.requestsOnly:
							yield line
						self.parser = self.headers
				elif self.parser is self.headers:
					if ln is False:
						# We've parsed the headers
						headers = self.headers.flush()
						self.requestHeaders = headers
						if headers is not None and not self.requestsOnly:
							yield headers
						# If it's a method with no expected body, we skip the parsing
						# of the body.
						if (
							self.requestLine
							and isinstance(self.requestLine, HTTPRequestLine)
							and (
								self.requestLine.method not in self.METHOD_HAS_BODY
								or headers
								and headers.contentLength == 0
							)
						):
							line = self.requestLine
							# That's an early exit
							yield HTTPRequest(
								method=line.method,
								path=line.path,
								query=parseQuery(line.query),
								headers=headers or HTTPHeaders({}),
								protocol=line.protocol,
								# FIXME: Is there remaining content?
								body=_EMPTY_BODY,
							)
							self.parser = self.message.reset()
						elif (
							headers is not None
							and self.requestLine
							and isinstance(self.requestLine, HTTPRequestLine)
						):
							line = self.requestLine
							if headers.contentLength is None:
								transfer_encoding = headers.headers.get(
									"Transfer-Encoding"
								)
								if (
									transfer_encoding
									and transfer_encoding.strip().lower() != "identity"
								):
									# Chunked and other transfer encodings are not supported
									# by this parser yet.
									yield HTTPProcessingStatus.BadFormat
									self.parser = self.message.reset()
								else:
									# For requests with no body delimiter, we do not consume
									# arbitrary bytes from the stream (which could include a
									# pipelined request).
									yield HTTPRequest(
										method=line.method,
										path=line.path,
										query=parseQuery(line.query),
										headers=headers,
										protocol=line.protocol,
										body=_EMPTY_BODY,
									)
									self.parser = self.message.reset()
							else:
								self.parser = self.bodyLength.reset(
									headers.contentLength
								)
								yield HTTPProcessingStatus.Body
						elif headers is not None:
							if headers.contentLength is None:
								# FIXME: Not sure what the EOS parser was for
								# self.parser = self.bodyEOS.reset(b"\n")
								self.parser = self.bodyRest.reset()
								yield HTTPProcessingStatus.Body
							else:
								self.parser = self.bodyLength.reset(
									headers.contentLength
								)
								yield HTTPProcessingStatus.Body
					else:
						# `ln` is going to be the header name as a string there.
						pass
				elif (
					self.parser is self.bodyEOS
					or self.parser is self.bodyLength
					or self.parser is self.bodyRest
				):
					if self.requestLine is None or self.requestHeaders is None:
						yield HTTPProcessingStatus.BadFormat
					else:
						# FIXME: In some circumstances (for POST requests),
						# reading the body will time out, and then the request
						# will be duplicated.
						headers = self.requestHeaders
						line = self.requestLine
						# NOTE: This is an awkward dance around the type checker
						# All body parsers return HTTPBodyBlob
						body: HTTPBodyBlob
						if self.parser is self.bodyEOS:
							body = self.bodyEOS.flush()
						elif self.parser is self.bodyLength:
							body = self.bodyLength.flush()
						elif self.parser is self.bodyRest:
							body = self.bodyRest.flush()
						else:
							# Should not happen
							body = HTTPBodyBlob()
						# NOTE: Careful here as we may create a request that has
						# a body with remaining data. The HTTP request will need
						# to make sure it can continue reading the body.
						if isinstance(line, TLSHandshake):
							# Skip TLS handshake for now
							pass
						elif isinstance(line, HTTPRequestLine):
							yield HTTPRequest(
								method=line.method,
								protocol=line.protocol,
								path=line.path,
								query=parseQuery(line.query),
								headers=headers,
								body=body,
							)
						elif isinstance(line, HTTPResponseLine):
							yield HTTPResponse(
								protocol=line.protocol,
								status=line.status,
								message=line.message,
								headers=headers,
								body=body,
							)
					self.parser = self.message.reset()
				else:
					raise RuntimeError(f"Unsupported parser: {self.parser}")
				# NOTE: Need to make sure the indentation is correct here
				# We increase the offset with the read bytes
				offset += read


class CookieValue(NamedTuple):
	key: str
	value: str | None
	start: int
	end: int


def iparseCookie(text: str) -> Iterator[CookieValue]:
	o = 0
	n = len(text)
	while o < n:
		# We look for a `;` field separator
		i = text.find(";", o)
		if i == -1:
			i = n
		# We look for a `=` value separator separator
		j = text.find("=", o)
		if j == -1 or j > i:
			# We don't have a value
			yield CookieValue(text[o:i].strip(), None, o, i)
		else:
			yield CookieValue(text[o:j].strip(), text[j + 1 : i].strip(), o, i)
		o = i + 1


def parseCookie(text: str) -> list[CookieValue]:
	return list(iparseCookie(text))


def formatCookie(cookies: Iterable[CookieValue]) -> str:
	return "; ".join(
		_.key if _.value is None else f"{_.key}={_.value}" for _ in cookies
	)


def parseQuery(text: str) -> dict[str, str]:
	if not text:
		return EmptyQuery
	res: dict[str, str] = {}
	for item in text.split("&"):
		if not item:
			continue
		kv = item.split("=", 1)
		if len(kv) == 1:
			res[item] = ""
		else:
			res[kv[0]] = kv[1]
	return res


# EOF
