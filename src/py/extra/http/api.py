from abc import ABC, abstractmethod
from base64 import b64encode
from pathlib import Path
from typing import Any, Generic, Iterator, TypeVar

from ..utils.codec import ENCODING_EXT, ENCODING_PRIORITY, parseAcceptEncoding
from ..utils.files import contentType as getContentType, resolveSuffix
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
		acceptEncoding: str | None = None,
	) -> T:
		"""Respond with a file, optionally serving pre-compressed variants.

		If acceptEncoding is provided (from Accept-Encoding header), and a
		pre-compressed file exists (e.g., file.js.gz or file.js.br), it will
		be served with the appropriate Content-Encoding header.

		Args:
		    path: Path to the file to serve
		    headers: Additional headers to include
		    status: HTTP status code
		    contentType: Override content type (defaults to guessing from path)
		    acceptEncoding: Value of Accept-Encoding header for compression negotiation
		"""
		p: Path = path if isinstance(path, Path) else Path(path)
		actualPath: Path = p
		encoding: str | None = None

		# Try to find a pre-compressed version if client accepts compression
		if acceptEncoding:
			accepted = parseAcceptEncoding(acceptEncoding)
			# Build suffix list in priority order for accepted encodings
			suffixes = [
				ENCODING_EXT[enc] for enc in ENCODING_PRIORITY if enc in accepted
			]
			if suffixes:
				if match := resolveSuffix(p, suffixes):
					actualPath, ext = match
					# Map extension back to encoding name
					encoding = next(
						(enc for enc, e in ENCODING_EXT.items() if e == ext), None
					)

		# Content type is based on original file, not compressed version
		ctype: str = contentType or getContentType(p)
		clen: str = str(actualPath.stat().st_size)

		baseHeaders: dict[str, str] = {
			"Content-Type": ctype,
			"Content-Length": clen,
		}

		# Add encoding header if serving compressed file
		if encoding:
			baseHeaders["Content-Encoding"] = encoding

		# Add Vary header for proper caching when compression is possible
		if acceptEncoding:
			baseHeaders["Vary"] = "Accept-Encoding"

		return self.respond(
			content=actualPath,
			status=status,
			headers=baseHeaders | headers if headers else baseHeaders,
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
