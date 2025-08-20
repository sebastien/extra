from abc import ABC, abstractmethod
from typing import NamedTuple, TypeAlias, Generic, TypeVar
from ..utils.io import LineParser, Control, EOS


# --
# TODO: We need to be able to write TODO
#
# 1) A file (for spooling)
# 2) A memory buffer (when we know the size of the body)
# 3) Process as we go (streaming)

T = TypeVar("T")


class Processor(ABC, Generic[T]):
	@abstractmethod
	def accepts(self, headers: dict[str, str]) -> bool:
		...

	@abstractmethod
	def start(self, headers: dict[str, str]) -> int:
		...

	@abstractmethod
	def feed(self, chunk: bytes) -> T | Control:
		...


# -----------------------------------------------------------------------------
#
# MULTIPART
#
# -----------------------------------------------------------------------------


class MultipartBoundary(NamedTuple):
	boundary: str


class MultipartHeaders(NamedTuple):
	headers: dict[str, str]


class MultipartData(NamedTuple):
	data: bytes


MultipartOutput: TypeAlias = MultipartBoundary | MultipartHeaders | MultipartData


class Multipart(Processor[MultipartOutput]):
	# NOTE: We encountered some problems with the `email` module in Python 3.4,
	# which lead to writing these functions.
	# http://stackoverflow.com/questions/4526273/what-does-enctype-multipart-form-data-mean

	def __init__(self, *, size: int = 64_000):
		self.boundary: bytes | None = None
		self.boundaryLength: int = 0
		self.hasMore: bool = True
		self.size: int = size
		self.line = LineParser()

	def accepts(self, headers: dict[str, str]) -> bool:
		# multipart/form-data
		# The contentType is expected to be
		# >   Content-Type: multipart/form-data; boundary=<BOUNDARY>\r\n
		content_type = headers.get("Content-Type")
		return bool(
			content_type
			and (
				"multipart/form-data" in content_type
				or "multipart/mixed" in content_type
			)
		)

	def start(self, headers: dict[str, str]) -> int:
		content_type = headers["Content-Type"]
		self.boundary = f"--{content_type.split('boundary=', 1)[1]}".encode("ascii")
		self.boundaryLength = len(self.boundary)
		self.line.reset(self.boundary)
		self.hasMore = True
		return self.boundaryLength + self.size

	def feed(self, chunk: bytes) -> MultipartOutput | Control:
		# TODO: implement this
		return EOS


# EOF
