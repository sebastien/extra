from abc import ABC, abstractmethod
from base64 import b64encode
from pathlib import Path
from typing import Any, Generic, Iterator, TypeVar

from ..utils.files import contentType as getContentType
from ..utils.json import json
from .status import HTTP_STATUS

T = TypeVar("T")

# -----------------------------------------------------------------------------
#
# API
#
# -----------------------------------------------------------------------------

# --
# == HTTP Request Response API
#
# Defines the high level API functions (orthogonal to the underlying model)
# to manipulate requests/responses.


class ResponseFactory(ABC, Generic[T]):
	@abstractmethod
	def respond(
		self,
		content: Any = None,
		contentType: str | None = None,
		contentLength: int | None = None,
		status: int = 200,
		headers: dict[str, str] | None = None,
		message: str | None = None,
	) -> T: ...

	def empty(
		self,
		status: int = 200,
		headers: dict[str, str] | None = None,
	) -> T:
		return self.respond(
			content=None,
			contentType=None,
			status=status,
			headers=headers,
		)

	def error(
		self,
		status: int,
		content: str | None = None,
		contentType: str = "text/plain",
		headers: dict[str, str] | None = None,
	) -> T:
		message = HTTP_STATUS.get(status, "Server Error")
		return self.respond(
			content=message if content is None else content,
			contentType=contentType,
			status=status,
			message=message,
			headers=headers,
		)

	def notAuthorized(
		self,
		content: str = "Unauthorized",
		contentType: str = "text/plain",
		*,
		status: int = 403,
	) -> T:
		return self.error(status, content=content, contentType=contentType)

	def notFound(
		self,
		content: str = "Not Found",
		contentType: str = "text/plain",
		*,
		status: int = 404,
	) -> T:
		return self.error(status, content=content, contentType=contentType)

	def notModified(self) -> None:
		raise NotImplementedError

	def fail(
		self,
		content: str | None = None,
		*,
		status: int = 500,
		contentType: str = "text/plain",
	) -> T:
		return self.respondError(
			content=content, status=status, contentType=contentType
		)

	def redirect(self, url: str, permanent: bool = False) -> T:
		# SEE: https://developer.mozilla.org/en-US/docs/Web/HTTP/Redirections
		return self.respondEmpty(
			status=301 if permanent else 302, headers={"Location": str(url)}
		)

	def returns(
		self,
		value: Any,
		headers: dict[str, str] | None = None,
		*,
		status: int = 200,
		contentType: str = "application/json",
	) -> T:
		if isinstance(value, bytes):
			try:
				value = value.decode("ascii")
			except UnicodeDecodeError:
				value = f"base64:{b64encode(value).decode('ascii')}"
		payload: bytes = json(value)
		return self.respond(
			payload,
			contentType=contentType,
			contentLength=len(payload),
			headers=headers,
			status=status,
		)

	def respondText(
		self,
		content: str | bytes | Iterator[str | bytes],
		contentType: str = "text/plain",
		status: int = 200,
	) -> T:
		return self.respond(content=content, contentType=contentType, status=status)

	def respondHTML(
		self, html: str | bytes | Iterator[str | bytes], status: int = 200
	) -> T:
		return self.respond(content=html, contentType="text/html", status=status)

	# TODO: Support (req) Range: bytes=100-200
	# TODO: Support (res) Content-Range: bytes 100-200/1000 (start-end/size)
	def respondFile(
		self,
		path: Path | str,
		headers: dict[str, str] | None = None,
		status: int = 200,
		contentType: str | None = None,
	) -> T:
		# TODO: We should have a much more detailed file handling, supporting ranges, etags, etc.
		p: Path = path if isinstance(path, Path) else Path(path)
		content_type: str = contentType or getContentType(p)
		content_length: str = str(p.stat().st_size)
		base_headers = {"Content-Type": content_type, "Content-Length": content_length}
		return self.respond(
			content=path if isinstance(path, Path) else Path(path),
			status=status,
			headers=base_headers | headers if headers else base_headers,
		)

	def respondError(
		self,
		content: str | None = None,
		contentType: str = "text/plain",
		*,
		status: int = 500,
	) -> T:
		return self.error(status, content, contentType)

	def respondEmpty(self, status: int, headers: dict[str, str] | None = None) -> T:
		return self.respond(content=None, status=status, headers=headers)


# EOF
