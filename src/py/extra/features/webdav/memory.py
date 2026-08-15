"""A deterministic in-memory backend for WebDAV services and tests."""

from __future__ import annotations

from hashlib import md5
from time import time
from typing import AsyncIterator, Iterable, Mapping

from ...utils.files import contentType
from .model import (
	WebDAVCapabilities,
	WebDAVConflict,
	WebDAVPreconditionFailed,
	WebDAVProperty,
	WebDAVResource,
)


def _path(path: str) -> str:
	parts = [part for part in path.replace("\\", "/").split("/") if part]
	if any(part in (".", "..") for part in parts):
		raise ValueError(f"Invalid WebDAV path: {path}")
	return "/" + "/".join(parts) if parts else "/"


class MemoryWebDAVBackend:
	"""A small read-only tree built from paths mapped to bytes or text."""

	def __init__(
		self,
		files: dict[str, bytes | str] | None = None,
		collections: Iterable[str] = (),
		*,
		writable: bool = False,
	) -> None:
		self.capabilities = WebDAVCapabilities(
			put=writable,
			mkcol=writable,
			delete=writable,
			copy=writable,
			move=writable,
			propertyWrite=writable,
		)
		now = time()
		self.resources: dict[str, WebDAVResource] = {
			"/": WebDAVResource("/", "", True, modifiedAt=now, createdAt=now)
		}
		self.contents: dict[str, bytes] = {}
		self.properties: dict[str, dict[str, WebDAVProperty]] = {}
		for path in collections:
			self.addCollection(path, now=now)
		for path, data in (files or {}).items():
			self.addFile(path, data, now=now)

	def addCollection(self, path: str, *, now: float | None = None) -> None:
		path = _path(path)
		stamp = time() if now is None else now
		if path == "/":
			return
		parent, _, name = path.rpartition("/")
		self.addCollection(parent or "/", now=stamp)
		self.resources[path] = WebDAVResource(
			path, name, True, modifiedAt=stamp, createdAt=stamp
		)

	def addFile(
		self,
		path: str,
		data: bytes | str,
		*,
		now: float | None = None,
		contentTypeValue: str | None = None,
	) -> None:
		path = _path(path)
		if path == "/":
			raise ValueError("The WebDAV root must be a collection")
		payload = data.encode("utf8") if isinstance(data, str) else data
		stamp = time() if now is None else now
		parent, _, name = path.rpartition("/")
		self.addCollection(parent or "/", now=stamp)
		self.contents[path] = payload
		self.resources[path] = WebDAVResource(
			path=path,
			name=name,
			collection=False,
			size=len(payload),
			contentType=contentTypeValue or contentType(name),
			modifiedAt=stamp,
			createdAt=stamp,
			etag='"' + md5(payload, usedforsecurity=False).hexdigest() + '"',  # nosec
		)

	async def stat(self, path: str) -> WebDAVResource | None:
		return self.resources.get(_path(path))

	async def iterChildren(self, path: str) -> AsyncIterator[WebDAVResource]:
		path = _path(path)
		prefix = "" if path == "/" else path
		depth = len([part for part in path.split("/") if part]) + 1
		for child in sorted(self.resources.values(), key=lambda item: item.path):
			if child.path.startswith(prefix + "/") and len(
				[part for part in child.path.split("/") if part]
			) == depth:
				yield child

	async def open(
		self, path: str, start: int | None = None, end: int | None = None
	) -> bytes:
		payload = self.contents[_path(path)]
		return payload[(start or 0) : end + 1 if end is not None else None]

	def _requireWritable(self) -> None:
		if not self.capabilities.put:
			raise WebDAVPreconditionFailed("Backend is read-only")

	def _requireParent(self, path: str) -> None:
		parent = path.rpartition("/")[0] or "/"
		resource = self.resources.get(parent)
		if resource is None or not resource.collection:
			raise WebDAVConflict(f"Parent collection does not exist: {parent}")

	def _children(self, path: str) -> list[str]:
		prefix = path.rstrip("/") + "/"
		return [key for key in self.resources if key.startswith(prefix)]

	async def write(
		self,
		path: str,
		content: AsyncIterator[bytes],
		*,
		contentType: str | None = None,
	) -> WebDAVResource:
		self._requireWritable()
		path = _path(path)
		if path == "/":
			raise WebDAVConflict("Cannot write a collection as a file")
		self._requireParent(path)
		payload = bytearray()
		async for chunk in content:
			payload.extend(chunk)
		self.addFile(path, bytes(payload), contentTypeValue=contentType)
		return self.resources[path]

	async def makeCollection(self, path: str) -> WebDAVResource:
		self._requireWritable()
		path = _path(path)
		if path in self.resources:
			raise WebDAVConflict(f"Resource already exists: {path}")
		self._requireParent(path)
		self.addCollection(path)
		return self.resources[path]

	async def delete(self, path: str) -> None:
		self._requireWritable()
		path = _path(path)
		if path == "/" or path not in self.resources:
			raise KeyError(path)
		for child in self._children(path):
			self.resources.pop(child, None)
			self.contents.pop(child, None)
		self.resources.pop(path, None)
		self.contents.pop(path, None)

	async def copy(
		self, source: str, destination: str, *, overwrite: bool = True
	) -> WebDAVResource:
		self._requireWritable()
		source = _path(source)
		destination = _path(destination)
		if source not in self.resources:
			raise KeyError(source)
		if destination in self.resources:
			if not overwrite:
				raise WebDAVPreconditionFailed("Destination exists")
			await self.delete(destination)
		self._requireParent(destination)
		paths = [source, *self._children(source)]
		for old in paths:
			relative = old[len(source) :]
			new = destination + relative
			resource = self.resources[old]
			self.resources[new] = WebDAVResource(
				path=new,
				name=new.rpartition("/")[2],
				collection=resource.collection,
				size=resource.size,
				contentType=resource.contentType,
				modifiedAt=resource.modifiedAt,
				createdAt=resource.createdAt,
				etag=resource.etag,
			)
			if old in self.contents:
				self.contents[new] = self.contents[old]
		return self.resources[destination]

	async def move(
		self, source: str, destination: str, *, overwrite: bool = True
	) -> WebDAVResource:
		resource = await self.copy(source, destination, overwrite=overwrite)
		await self.delete(source)
		return resource

	async def getProperties(
		self, path: str, names: set[str] | None = None
	) -> Mapping[str, WebDAVProperty]:
		resource = self.resources[_path(path)]
		properties = self.properties.get(resource.path, {})
		return properties if names is None else {
			name: value for name, value in properties.items() if name in names
		}

	async def setProperties(
		self, path: str, changes: Mapping[str, WebDAVProperty | None]
	) -> Mapping[str, int]:
		self._requireWritable()
		path = _path(path)
		if path not in self.resources:
			raise KeyError(path)
		properties = self.properties.setdefault(path, {})
		for name, value in changes.items():
			if value is None:
				properties.pop(name, None)
			else:
				properties[name] = value
		return {name: 200 for name in changes}


# EOF
