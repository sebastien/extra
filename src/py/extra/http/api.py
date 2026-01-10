from abc import ABC, abstractmethod
from base64 import b64encode
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Generic, Iterator, TypeVar

from ..utils.codec import ENCODING_EXT, ENCODING_PRIORITY, parseAcceptEncoding
from ..utils.files import (
	contentType as getContentType,
	fileEtag,
	parseRange,
	resolveSuffix,
)
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

	def respondFile(
		self,
		path: Path | str,
		headers: dict[str, str] | None = None,
		status: int = 200,
		contentType: str | None = None,
		acceptEncoding: str | None = None,
		ifNoneMatch: str | None = None,
		ifModifiedSince: str | None = None,
		ifRange: str | None = None,
		rangeHeader: str | None = None,
	) -> T:
		"""Respond with a file, supporting compression, ETags, and Range requests.

		Features:
		- Pre-compressed file variants (.gz, .br) when acceptEncoding is provided
		- ETag generation and If-None-Match conditional requests (304 responses)
		- If-Modified-Since conditional requests (304 responses)
		- Range requests for partial content (206 responses)
		- If-Range for conditional range requests

		Args:
		    path: Path to the file to serve
		    headers: Additional headers to include (can override ETag/Last-Modified)
		    status: HTTP status code (may be overridden for 304/206/416)
		    contentType: Override content type (defaults to guessing from path)
		    acceptEncoding: Accept-Encoding header for compression negotiation
		    ifNoneMatch: If-None-Match header for conditional requests
		    ifModifiedSince: If-Modified-Since header for conditional requests
		    ifRange: If-Range header for conditional range requests
		    rangeHeader: Range header for partial content requests
		"""
		p: Path = path if isinstance(path, Path) else Path(path)
		actualPath: Path = p
		encoding: str | None = None

		# Try to find a pre-compressed version if client accepts compression
		if acceptEncoding:
			accepted = parseAcceptEncoding(acceptEncoding)
			suffixes = [
				ENCODING_EXT[enc] for enc in ENCODING_PRIORITY if enc in accepted
			]
			if suffixes:
				if match := resolveSuffix(p, suffixes):
					actualPath, ext = match
					encoding = next(
						(enc for enc, e in ENCODING_EXT.items() if e == ext), None
					)

		# Get file stats for ETag and Last-Modified
		stat = actualPath.stat()
		fileSize: int = stat.st_size

		# Generate or use provided ETag
		etag: str = (headers or {}).get("ETag") or fileEtag(actualPath)

		# Generate Last-Modified from file mtime
		from email.utils import formatdate

		lastModified: str = (headers or {}).get("Last-Modified") or formatdate(
			stat.st_mtime, usegmt=True
		)

		# Content type is based on original file, not compressed version
		ctype: str = contentType or getContentType(p)

		# Base headers always included
		baseHeaders: dict[str, str] = {
			"Content-Type": ctype,
			"ETag": etag,
			"Last-Modified": lastModified,
			"Accept-Ranges": "bytes",
		}

		# Add encoding header if serving compressed file
		if encoding:
			baseHeaders["Content-Encoding"] = encoding

		# Add Vary header for caching when compression negotiation is used
		if acceptEncoding:
			baseHeaders["Vary"] = "Accept-Encoding"

		# --
		# Check conditional headers (per RFC 7232 precedence)
		# --

		# If-None-Match: return 304 if ETag matches
		if ifNoneMatch:
			# Handle multiple ETags: If-None-Match: "a", "b", "c"
			# Also handle * which matches any
			clientEtags = [e.strip().strip('"') for e in ifNoneMatch.split(",")]
			serverEtag = etag.strip('"')
			if "*" in clientEtags or serverEtag in clientEtags:
				return self.respond(
					content=None,
					status=304,
					headers=baseHeaders | headers if headers else baseHeaders,
				)

		# If-Modified-Since: return 304 if file hasn't changed
		if ifModifiedSince and not ifNoneMatch:
			try:
				clientTime = parsedate_to_datetime(ifModifiedSince)
				from datetime import datetime, timezone

				fileTime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
				# File not modified if mtime <= client's cached time
				if fileTime <= clientTime:
					return self.respond(
						content=None,
						status=304,
						headers=baseHeaders | headers if headers else baseHeaders,
					)
			except (ValueError, TypeError):
				# Invalid date format, ignore and serve full content
				pass

		# --
		# Handle Range requests
		# --

		rangeStart: int | None = None
		rangeEnd: int | None = None

		if rangeHeader and fileSize > 0:
			# If-Range: only serve partial if ETag matches, else serve full
			if ifRange:
				ifRangeEtag = ifRange.strip().strip('"')
				if ifRangeEtag != etag.strip('"'):
					# ETag doesn't match, serve full content (ignore Range)
					rangeHeader = None

			if rangeHeader:
				parsed = parseRange(rangeHeader, fileSize)
				if parsed is None:
					# Invalid or unsatisfiable range
					return self.respond(
						content=None,
						status=416,
						headers={
							"Content-Range": f"bytes */{fileSize}",
							"Content-Type": ctype,
						},
					)
				rangeStart, rangeEnd = parsed

		# --
		# Build response
		# --

		if rangeStart is not None and rangeEnd is not None:
			# Partial content response (206)
			# Import here to avoid circular import with model.py
			from .model import HTTPBodyFile

			contentLen = rangeEnd - rangeStart + 1
			baseHeaders["Content-Length"] = str(contentLen)
			baseHeaders["Content-Range"] = f"bytes {rangeStart}-{rangeEnd}/{fileSize}"

			body = HTTPBodyFile(
				path=actualPath.absolute(),
				start=rangeStart,
				end=rangeEnd,
			)

			return self.respond(
				content=body,
				status=206,
				headers=baseHeaders | headers if headers else baseHeaders,
			)
		else:
			# Full content response (200)
			baseHeaders["Content-Length"] = str(fileSize)

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
