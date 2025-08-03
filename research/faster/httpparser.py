from typing import Iterator, ClassVar

# NOTE: Headers as strings, not bytes, it's all ASCII.

# This is a simple HTTP parser based on mini composable parsers (request,
# headers and specialized body). The all work so that they can be fed data.
from io import BytesIO
from enum import Enum


EOL: bytes = b"\r\n"


# NOTE:Parse at through=232.92Mb/s with PyPy vs 54.80Mb/s (Py312)
class LineParser:
	__slots__ = ["data", "eol"]

	def __init__(self) -> None:
		self.data: list[bytes] = []
		self.eol: bytes = EOL

	def reset(self, eol: bytes = EOL) -> "LineParser":
		self.data.clear()
		self.eol = eol
		return self

	def flushstr(self) -> str:
		res: str = b"".join(self.data).decode("ascii")
		self.data.clear()
		return res

	def feed(self, chunk: bytes, start: int = 0) -> tuple[list[bytes] | None, int]:
		end = chunk.find(self.eol, start)
		if end == -1:
			self.data.append(chunk[start:] if start else chunk)
			return None, len(chunk) - start
		else:
			self.data.append(chunk[start:end])
			return self.data, (end + 2) - start


# NOTE:Parse at through=182.01Mb/s with PyPy vs 51.47Mb/s (Py312)
class LineIOParser:
	__slots__ = ["data", "eol", "written"]

	def __init__(self) -> None:
		self.data: BytesIO = BytesIO()
		self.eol: bytes = EOL
		self.written: int = 0

	def reset(self, eol: bytes = EOL) -> "LineIOParser":
		self.data.seek(0)
		self.written = 0
		return self

	def flushstr(self) -> str:
		self.data.seek(0)
		res = self.data.read(self.written).decode("ascii")
		self.reset()
		return res

	def feed(self, chunk: bytes, start: int = 0) -> tuple[BytesIO | None, int]:
		end = chunk.find(self.eol, start)
		n = len(chunk)
		if end == -1:
			w = n - start
			self.data.write(chunk[start:] if start else chunk)
			self.written += w
			return None, w
		else:
			self.data.write(chunk[start:end])
			w = end - start
			self.written += w
			return self.data, w + 2


# FIXME: Not working and slow: 28.11Mb/s (Py3.12) and 45.21 (PyPy3)
class LineBufferParser:
	__slots__ = ["buffer", "eol"]

	def __init__(self) -> None:
		self.buffer = bytearray()
		self.eol: bytes = EOL

	def reset(self, eol: bytes = EOL) -> "LineBufferParser":
		self.eol = eol
		return self

	def feed(self, chunk: bytes, start: int = 0) -> tuple[bytes | None, int]:
		line_end = chunk.find(self.eol, start)
		if line_end == -1:
			self.buffer += chunk[start:] if start else chunk
			return None, len(chunk) - start
		else:
			self.buffer += chunk[start:line_end]
			res = bytes(self.buffer[:])
			del self.buffer[:]
			self.buffer += chunk[line_end + 2 :]
			return res, line_end - start + 2


class RequestParser:
	__slots__ = ["line", "method", "path", "protocol"]

	def __init__(self) -> None:
		self.line: LineParser = LineParser()
		self.method: str = ""
		self.path: str = ""
		self.protocol: str = ""

	def reset(self) -> "RequestParser":
		self.line.reset()
		self.method = ""
		self.path = ""
		self.protocol = ""
		return self

	def feed(self, chunk: bytes, start: int = 0) -> tuple[bool | None, int]:
		chunks, end = self.line.feed(chunk, start)
		if chunks:
			# NOTE: This is safe
			cl = b"".join(chunks).decode("ascii")
			i = cl.find(" ")
			j = cl.rfind(" ")
			# NOTE: There may be junk before the method name
			self.method = cl[0:i]
			self.path = cl[i + 1 : j]
			self.protocol = cl[j + 1 :]
			return True, end
		else:
			return None, end

	def __str__(self) -> str:
		return f"RequestParser({self.method} {self.path} {self.protocol})"


class HeadersParser:
	__slots__ = ["previous", "headers", "contentType", "contentLength", "line"]

	def __init__(self) -> None:
		super().__init__()
		self.headers: dict[str, str] = {}
		self.line: LineParser = LineParser()
		self.contentType: str | None = None
		self.contentLength: int | None = None
		# TODO: Close header
		# self.close:bool = False

	def reset(self) -> "HeadersParser":
		self.line.reset()
		self.headers.clear()
		self.contentType = None
		self.contentLength = None
		return self

	def feed(self, chunk: bytes, start: int = 0) -> tuple[bool | None, int]:
		chunks, end = self.line.feed(chunk, start)
		if chunks is None:
			return None, end
		elif chunks:
			ln = self.line.flushstr()
			i = ln.find(":")
			if not ln:
				return False, end
			elif i != -1:
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
				self.headers[h] = v
				return True, end
			else:
				return None, end
		else:
			# An empty line denotes the end of headers
			return False, end

	def __str__(self) -> str:
		return f"HeadersParser({self.headers})"


class BodyEOSParser:
	__slots__ = ["line"]

	def __init__(self) -> None:
		self.line = LineParser()

	def reset(self, eos: bytes = EOL) -> "BodyEOSParser":
		self.line.reset(eos)
		return self

	def feed(self, chunk: bytes, start: int = 0) -> tuple[list[bytes] | None, int]:
		chunks, end = self.line.feed(chunk, start)
		if chunks is None:
			return None, end
		else:
			res = chunks.copy()
			self.line.reset()
			return res, end


class BodyLengthParser:
	"""Parses the body of a request with ContentLength set"""

	__slots__ = ["expected", "read", "data"]

	def __init__(self) -> None:
		self.expected: int = 0
		self.read: int = 0
		self.data: list[bytes] = []

	def reset(self, length: int) -> "BodyLengthParser":
		self.expected = length
		self.read = 0
		self.data.clear()
		return self

	def feed(self, chunk: bytes, start: int = 0) -> tuple[bool, int]:
		n: int = len(chunk) - start
		to_read: int = self.expected - self.read
		if to_read < n:
			self.data.append(chunk[start:to_read])
			return False, to_read
		elif to_read == n:
			self.data.append(chunk[start:] if start else chunk)
			return False, n
		else:
			self.data.append(chunk[start:] if start else chunk)
			return True, n


class HTTPParserStatus(Enum):
	Request = 0
	Headers = 1
	Body = 2
	Complete = 2


class HTTPParser:
	HAS_BODY: ClassVar[set[str]] = {"POST", "PUT", "PATCH"}

	def __init__(self) -> None:
		self.request: RequestParser = RequestParser()
		self.headers: HeadersParser = HeadersParser()
		self.bodyEOS: BodyEOSParser = BodyEOSParser()
		self.bodyLength: BodyLengthParser = BodyLengthParser()
		self.parser: (
			RequestParser | HeadersParser | BodyEOSParser | BodyLengthParser
		) = self.request

	def feed(self, chunk: bytes) -> Iterator[HTTPParserStatus]:
		size: int = len(chunk)
		o: int = 0
		while o < size:
			ln, n = self.parser.feed(chunk, o)
			if ln is not None:
				if self.parser is self.request:
					yield HTTPParserStatus.Request
					self.parser = self.headers.reset()
				elif self.parser is self.headers:
					if ln is False:
						yield HTTPParserStatus.Headers
						if self.request.method not in self.HAS_BODY:
							yield HTTPParserStatus.Complete
						else:
							match self.headers.contentLength:
								case None:
									self.parser = self.bodyEOS.reset(b"\n")
									yield HTTPParserStatus.Body
								case int(n):
									self.parser = self.bodyLength.reset(n)
									yield HTTPParserStatus.Body
				elif self.parser is self.bodyEOS:
					yield HTTPParserStatus.Complete
					self.parser = self.headers.reset()
				elif self.parser is self.bodyLength:
					yield HTTPParserStatus.Complete
					self.parser = self.request.reset()
				else:
					raise RuntimeError(f"Unsupported parser: {self.parser}")
			o += n
			if not n:
				print("Not sure this is good", o)
				break


if __name__ == "__main__":
	import time
	from pathlib import Path

	BASE: Path = Path(__file__).absolute().parent.parent.parent

	# NOTE: requests are separated by a `\n`
	with open(BASE / "data/csic_2010-normalTrafficTraining.txt", "rb") as f:
		request_parser = RequestParser()
		header_parser = HeadersParser()
		body_length_parser = BodyLengthParser()
		body_eos_parser = BodyEOSParser()
		parser: (
			LineIOParser
			| RequestParser
			| HeadersParser
			| BodyLengthParser
			| BodyEOSParser
		) = request_parser
		size = 2048
		i = 0
		print("\n\n==============")
		t = time.monotonic()
		count = 0
		total: int = 0
		while count < 20:
			o: int = 0
			chunk: bytes = f.read(size)
			if not chunk:
				break
			while o < size:
				ln, n = parser.feed(chunk, o)
				print(
					f"Chunk {repr(chunk[o : o + n])}={ln} from {parser.__class__.__name__}"
				)
				# FIXME: That doesn't quite work yet
				if ln is not None:
					if parser is request_parser:
						parser = header_parser.reset()
					elif parser is header_parser:
						if ln is False:
							if header_parser.contentLength is None:
								parser = body_eos_parser.reset(b"\n")
							else:
								parser = body_length_parser.reset(
									header_parser.contentLength
								)
					elif parser is body_eos_parser:
						parser = request_parser.reset()
					elif parser is body_length_parser:
						parser = request_parser.reset()
					count += 1
				o += n
				if not n:
					break
			total += len(chunk)
			i += 1
		elapsed = time.monotonic() - t
		# ## With a bzip2 source:
		# Reading chunks:
		#  - 37.45Mb/s size=2048
		# Reading lines:
		# - 24.12Mb/s size=2048
		# Reading lines, headers & bodies:
		# - 14.41Mb/s (Py3.12)
		# - 15.11Mb/s (MyPyC)
		# - 21.14Mb/s (PyPy)
		# ## With a text source:
		# Reading lines, headers & bodies:
		# - 25.76Mb/s (Py3.12)
		# - 28.14Mb/s (MyPyC)
		# - 86.96Mb/s (PyPy)

		print(
			f"Elapsed: {count}/{elapsed:0.2f}s through={(total / 1_000_000) / elapsed:0.2f}Mb/s size={size} count={count}"
		)

# EOF
