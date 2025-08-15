from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


class URI:
	__slots__ = (
		"path",
		"scheme",
		"host",
		"port",
		"params",
		"query",
		"fragment",
		"isLocal",
		"ext",
	)

	@classmethod
	def Parse(cls, link: "URI|str") -> "URI":
		if isinstance(link, URI):
			return link
		# FIXME: This does not work well, especially if the URL does not
		# have a scheme, like "google.com/hello" would not match the host
		# as expected.
		res = urlparse(link)
		host_port = res.netloc.split(":") if res.netloc else None
		return URI(
			scheme=res.scheme if res.scheme else None,
			host=host_port[0] if host_port else None,
			port=int(host_port[1]) if host_port and len(host_port) == 2 else None,
			path=res.path,
			params=res.params if res.params else None,
			query=res.query if res.query else None,
			fragment=res.fragment if res.fragment else None,
		)

	@classmethod
	def FromDict(cls, value: dict[str, Any]) -> "URI":
		return URI(
			path=value.get("path"),
			scheme=value.get("scheme"),
			host=value.get("host"),
			port=value.get("port"),
			params=value.get("params"),
			query=value.get("query"),
			fragment=value.get("fragment"),
		)

	def __init__(
		self,
		*,
		path: str | None = None,
		scheme: str | None = None,
		host: str | None = None,
		port: int | None = None,
		params: str | None = None,
		query: str | None = None,
		fragment: str | None = None,
	):
		self.path = path
		self.scheme = scheme
		self.host = host
		self.port = port
		self.params = params
		self.query = query
		self.fragment = fragment
		self.isLocal: bool = self.host is None
		self.ext = self.path.rsplit(".", 1)[1] if self.path and "." in self.path else ""

	@property
	def ssl(self) -> bool | None:
		return (
			True
			if self.port == 443 or self.scheme in ("https", None)
			else False
			if self.scheme == "http"
			else None
		)

	@property
	def site(self) -> "URI":
		return URI(scheme=self.scheme, host=self.host, port=self.port)

	@property
	def local(self) -> "URI":
		return URI(
			path=self.path, params=self.params, query=self.query, fragment=self.fragment
		)

	def asDict(self) -> dict[str, Any]:
		return {
			k: v
			for k, v in dict(
				path=self.path,
				scheme=self.scheme,
				host=self.host,
				port=self.port,
				params=self.params,
				query=self.query,
				fragment=self.fragment,
				# Synthetic
				ext=self.ext,
				isLocal=self.isLocal,
			).items()
			if v is not None
		}

	def merge(self, uri: "URI") -> "URI":
		return self.derive(
			path=uri.path,
			scheme=uri.scheme,
			host=uri.host,
			port=uri.port,
			params=uri.params,
			query=uri.query,
			fragment=uri.fragment,
		)

	def derive(
		self,
		path: str | None = None,
		scheme: str | None = None,
		host: str | None = None,
		port: int | None = None,
		params: str | None = None,
		query: str | None = None,
		fragment: str | None = None,
	) -> "URI":
		return URI(
			path=self.path if path is None else path,
			scheme=self.scheme if scheme is None else scheme,
			host=self.host if host is None else host,
			port=self.port if port is None else port,
			params=self.params if params is None else params,
			query=self.query if query is None else query,
			fragment=self.fragment if fragment is None else fragment,
		)

	def relativeTo(self, root: "URI") -> "URI":
		if self.isLocalTo(root):
			return URI(
				scheme=self.scheme or root.scheme,
				host=self.host or root.host,
				port=self.port or root.port,
				path=self.path,
				params=self.params,
				query=self.query,
				fragment=self.fragment,
			)
		else:
			return (
				self.derive(
					scheme=self.scheme or root.scheme,
					host=self.host or root.host,
					port=self.port or root.port,
				)
				if not (self.scheme and self.host and self.port)
				else self
			)

	def rebase(self, root: "URI") -> "URI":
		return URI(
			path=self.path,
			scheme=self.scheme or root.scheme,
			host=root.host,
			port=root.port,
			params=self.params,
			query=self.query,
			fragment=self.fragment,
		)

	def isLocalTo(self, root: "URI") -> bool:
		# NOTE: We don't mind scheme there
		if self.host and self.host != root.host:
			return False
		if self.port and self.port != root.port:
			return False
		else:
			return True

	def goTo(self, path: str) -> "URI":
		# FIXME: We should test if the path is absolute or not
		return self.derive(path=path)

	def __add__(self, other: "URI|str") -> "URI":
		return self.merge(URI.Parse(other))

	# FIXME: Not quite working, I think it may be the metaclasses
	def __div__(self, value: str) -> "URI":
		return self.derive(path=value)

	def __floordiv__(self, value: str) -> "URI":
		return self.derive(path=value)

	def __truediv__(self, value: str) -> "URI":
		return self.derive(path=value)

	def __eq__(self, other: Any) -> bool:
		if isinstance(other, str):
			return str(self) == other
		elif isinstance(other, URI):
			return (
				self.path == other.path
				and self.scheme == other.scheme
				and self.host == other.host
				and self.port == other.port
				and self.params == other.params
				and self.query == other.query
				and self.fragment == other.fragment
			)
		else:
			return False

	def __repr__(self) -> str:
		attr = dict(
			scheme=self.scheme,
			host=self.host,
			port=self.port,
			path=self.path,
			params=self.params,
			query=self.query,
			fragment=self.fragment,
		)
		return f"URI({' '.join(f'{k}={v}' for k, v in attr.items() if v)})"

	def __str__(self) -> str:
		res: list[str] = []
		# FIXME: We should reuse the URI part
		# SEE: https://stackoverflow.com/questions/39266970/what-is-the-difference-between-url-parameters-and-query-strings
		if self.scheme:
			res.append(self.scheme)
			res.append("://")
		if self.scheme or self.host:
			res.append(self.host or "127.0.0.1")
			if self.port:
				res.append(f":{self.port}")
		if self.path:
			res.append(self.path)
		if self.params:
			# Should we URL-encode?
			res.append(";")
			res.append(self.params)
		if self.query:
			# Should we URL-encode?
			res.append("?")
			res.append(self.query)
		if self.fragment:
			# Should we URL-encode?
			res.append("#")
			res.append(self.fragment)
		return "".join(res)


def uri(value: str | URI) -> URI:
	return value if isinstance(value, URI) else URI.Parse(value)


# EOF
