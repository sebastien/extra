from typing import NamedTuple
from .json import json
from .primitives import TPrimitive

DEFAULT_ENCODING: str = "utf8"
EOL: bytes = b"\r\n"
END: int = 1


class Control(NamedTuple):
	id: str


EOS = Control("EOS")


def asBytes(value: str | bytes) -> bytes:
	if isinstance(value, bytes):
		return value
	elif isinstance(value, str):
		return bytes(value, DEFAULT_ENCODING)
	elif value is None:
		return b""
	else:
		raise ValueError(f"Expected bytes or str, got: {value}")


def asWritable(value: str | bytes | bytearray | TPrimitive) -> bytes:
	if isinstance(value, bytes) or isinstance(value, bytearray):
		return value
	elif isinstance(value, str):
		return value.encode(DEFAULT_ENCODING)
	else:
		return json(value)


class LineParser:
	__slots__ = ["buffer", "buflen", "line", "eol", "eolsize", "offset"]

	def __init__(self) -> None:
		self.buffer: bytearray = bytearray()
		self.buflen: int = 0
		self.line: bytes | None = None
		self.offset: int = 0
		self.eol: bytes = EOL
		self.eolsize: int = len(EOL)

	def reset(self, eol: bytes = EOL) -> "LineParser":
		self.buffer.clear()
		self.buflen = 0
		# TODO: Should we have line reset?
		self.line = None
		self.offset = 0
		self.eol = eol
		self.eolsize = len(eol)
		return self

	def flush(self) -> bytes | None:
		return self.line

	def feed(self, chunk: bytes, start: int = 0) -> tuple[bytes | None, int]:
		"""Returns the matching line and how many bytes were read in chunk from start. When line is None,
		then the whole chunk has been processed."""
		pos = len(self.buffer)
		self.buffer += chunk[start:]
		end = self.buffer.find(self.eol, self.offset)
		if end == -1:
			self.offset = max(0, len(self.buffer) - self.eolsize + 1)
			return None, len(chunk) - start
		else:
			self.line = self.buffer[:end]
			# FIXME: It may not be .clear()?
			self.buffer.clear()
			self.offset = 0
			return self.line, (end - pos) + self.eolsize


# EOF
