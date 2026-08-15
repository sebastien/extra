"""Backend abstractions for read-only WebDAV collections."""

from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator, Mapping, Protocol


@dataclass(frozen=True, slots=True)
class WebDAVResource:
	"""Metadata for one backend resource, addressed by an absolute POSIX path."""

	path: str
	name: str
	collection: bool
	size: int | None = None
	contentType: str | None = None
	modifiedAt: float | None = None
	createdAt: float | None = None
	etag: str | None = None


@dataclass(frozen=True, slots=True)
class WebDAVCapabilities:
	"""Operations supported by one WebDAV backend."""

	get: bool = True
	head: bool = True
	propfind: bool = True
	ranges: bool = True
	put: bool = False
	mkcol: bool = False
	delete: bool = False
	copy: bool = False
	move: bool = False
	propertyRead: bool = True
	propertyWrite: bool = False
	locking: bool = False
	depthInfinity: bool = True


@dataclass(frozen=True, slots=True)
class WebDAVProperty:
	"""A backend property represented without XML concerns."""

	name: str
	value: str | None = None
	children: tuple["WebDAVProperty", ...] = ()


class WebDAVBackend(Protocol):
	"""A resource tree, optionally supporting WebDAV mutations and properties."""

	capabilities: WebDAVCapabilities

	async def stat(self, path: str) -> WebDAVResource | None: ...

	def iterChildren(self, path: str) -> AsyncIterator[WebDAVResource]: ...

	async def open(self, path: str, start: int | None = None, end: int | None = None) -> bytes | AsyncIterator[bytes]: ...

	async def write(
		self,
		path: str,
		content: AsyncIterator[bytes],
		*,
		contentType: str | None = None,
	) -> WebDAVResource: ...

	async def makeCollection(self, path: str) -> WebDAVResource: ...

	async def delete(self, path: str) -> None: ...

	async def copy(
		self, source: str, destination: str, *, overwrite: bool = True
	) -> WebDAVResource: ...

	async def move(
		self, source: str, destination: str, *, overwrite: bool = True
	) -> WebDAVResource: ...

	async def getProperties(
		self, path: str, names: set[str] | None = None
	) -> Mapping[str, WebDAVProperty]: ...

	async def setProperties(
		self, path: str, changes: Mapping[str, WebDAVProperty | None]
	) -> Mapping[str, int]: ...


class WebDAVUnsupported(Exception):
	"""Raised when a backend does not implement an enabled operation."""


class WebDAVConflict(Exception):
	"""Raised when a mutation conflicts with current backend state."""


class WebDAVPreconditionFailed(Exception):
	"""Raised when a conditional mutation does not match."""


# EOF
