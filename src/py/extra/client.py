import asyncio
import os
import ssl
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, AsyncGenerator, ClassVar, Iterator, NamedTuple, TypeVar, Union
from urllib.parse import quote_plus, urlparse

from .http.model import (
	HTTPAtom,
	HTTPBody,
	HTTPBodyAsyncStream,
	HTTPBodyBlob,
	HTTPBodyFile,
	HTTPBodyIO,
	HTTPBodyStream,
	HTTPHeaders,
	HTTPProcessingStatus,
	HTTPRequest,
	HTTPResponse,
)
from .http.parser import HTTPParser
from .utils.io import asWritable
from .utils.logging import event

# For Python 3.8 compatibility
ConnectionT = TypeVar("ConnectionT", bound="Connection")
ConnectionPoolT = TypeVar("ConnectionPoolT", bound="ConnectionPool")


# --
# An low level async HTTP client with connection pooling support.

# -----------------------------------------------------------------------------
#
# SSL
#
# -----------------------------------------------------------------------------

SSL_CLIENT_CONTEXT: ssl.SSLContext = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)

# This is on purpose so that we can force unverified requests for security testing.
SSL_CLIENT_UNVERIFIED_CONTEXT: ssl.SSLContext = (
	ssl._create_unverified_context()  # nosec: B323
)
try:
	import certifi

	SSL_CLIENT_CONTEXT.load_verify_locations(certifi.where())
except FileNotFoundError:
	SSL_CLIENT_CONTEXT.load_verify_locations()
except ImportError:
	pass


# -----------------------------------------------------------------------------
#
# CONNECTION POOLING
#
# -----------------------------------------------------------------------------


class Target(NamedTuple):
	"""A host/port target."""

	name: str
	port: int


class ConnectionTarget(NamedTuple):
	"""Represents the target of an HTTP(S) connection, which includes
	a possible proxy. This is used as keys for connection pools, hence
	the NamedTuple."""

	host: Target
	ssl: bool
	proxy: Union[Target, None] = None
	verified: bool = True

	@staticmethod
	def Make(
		host: str,
		port: Union[int, None] = None,
		ssl: bool = True,
		*,
		timeout: Union[float, None] = None,
		proxy: Union[str, None] = None,
		proxyPort: Union[int, None] = None,
		verified: bool = True,
	) -> "ConnectionTarget":
		"""Convenience wrapper to create a connection target."""
		return ConnectionTarget(
			host=Target(host, port if port is not None else 443 if ssl else 80),
			proxy=Target(proxy, proxyPort) if proxy and proxyPort else None,
			ssl=bool(ssl),
			verified=verified,
		)


CONNECTION_IDLE: float = 30.0


@dataclass
class Connection:
	"""Wraps an underlying HTTP(S) connection with its target
	information."""

	target: ConnectionTarget
	reader: asyncio.StreamReader
	writer: asyncio.StreamWriter
	idle: float
	until: Union[float, None]
	# NOTE: We put parsers here as they're typically per connection
	parser: HTTPParser
	# A streaming connection won't be reused
	isStreaming: bool = False

	def close(self: ConnectionT) -> ConnectionT:
		"""Closes the writer."""
		self.writer.close()
		self.until = None
		return self

	@property
	def isValid(self) -> Union[bool, None]:
		"""Tells if the connection is still valid."""
		return (time.monotonic() <= self.until) if self.until else None

	def touch(self: ConnectionT) -> ConnectionT:
		"""Touches the connection, bumping its `until` time."""
		self.until = time.monotonic() + self.idle
		return self

	@staticmethod
	async def Make(
		target: ConnectionTarget,
		*,
		timeout: Union[float, None] = None,
		idle: Union[float, None],
		verified: bool = True,
	) -> "Connection":
		"""Makes a connection to the given target, this sets up the proxy
		destination."""
		# If we have a proxy, we connect to it first
		cxn_host: str = target.proxy.name if target.proxy else target.host.name
		cxn_port: int = target.proxy.port if target.proxy else target.host.port
		# We create the underlying connection
		reader, writer = await asyncio.wait_for(
			asyncio.open_connection(
				host=cxn_host,
				port=cxn_port,
				ssl=(
					(
						SSL_CLIENT_CONTEXT
						if verified is not False
						else SSL_CLIENT_UNVERIFIED_CONTEXT
					)
					if bool(target.ssl)
					else None
				),
			),
			timeout=timeout,
		)
		# We return a wrapper there
		idle = idle or CONNECTION_IDLE
		return Connection(
			target,
			reader,
			writer,
			idle=idle,
			until=time.monotonic() + idle,
			parser=HTTPParser(),
		)


class ConnectionPool:
	"""Context-aware pool of connections."""

	All: ClassVar[ContextVar[list["ConnectionPool"]]] = ContextVar(
		"httpConnectionsPool"
	)

	@classmethod
	def Get(cls, *, idle: Union[float, None] = None) -> "ConnectionPool":
		"""Ensures that there's at least one connection pool in the current
		context."""

		pools = cls.All.get(None)
		pool: ConnectionPool = pools[-1] if pools else ConnectionPool(idle=idle)
		if pools is None:
			cls.All.set([pool])
		elif not pools:
			pools.append(pool)
		return pool

	@classmethod
	async def Connect(
		cls,
		target: ConnectionTarget,
		*,
		idle: Union[float, None] = None,
		timeout: Union[float, None] = None,
		verified: bool = True,
	) -> Connection:
		"""Returns a connection to the target from the pool (if the pool is available
		and has a valid connection to the target), or creates a new connection."""
		pools = cls.All.get(None)
		res = await (
			pools[-1].get(target)
			if pools
			else Connection.Make(target, idle=idle, timeout=timeout, verified=verified)
		)
		return res

	@classmethod
	def Release(cls, connection: Connection) -> bool:
		"""Releases the connection back into the pool. If the connection
		is invalid, it will be closed instead."""
		pools = cls.All.get(None)
		# TODO: Should we close the underling connection or not?
		# connection.underlying.close()
		if not connection.isValid:
			return False
		elif connection.isStreaming:
			connection.close()
			return False
		elif pools:
			# NOTE: We don't close the connection here, as we want to reuse it.
			pools[-1].put(connection)
			return True
		else:
			connection.close()
			return False

	@classmethod
	def Push(cls, *, idle: Union[float, None] = None) -> "ConnectionPool":
		pools = cls.All.get(None)
		if pools is None:
			pools = []
			cls.All.set(pools)
		pool = ConnectionPool(idle=idle)
		pools.append(pool)
		return pool

	@classmethod
	def Pop(cls) -> "ConnectionPool|None":
		pools = cls.All.get(None)
		return pools.pop().release() if pools else None

	def __init__(self, idle: Union[float, None] = None):
		self.connections: dict[ConnectionTarget, list[Connection]] = {}
		self.idle: Union[float, None] = idle

	def has(
		self,
		target: ConnectionTarget,
	) -> bool:
		return any(_.isValid is True for _ in self.connections.get(target) or ())

	async def get(
		self,
		target: ConnectionTarget,
		*,
		idle: Union[float, None] = None,
	) -> Connection:
		cxn = self.connections.get(target)
		# We look for connections, which must be valid. If not valid,
		# then we close the connection, or return a new one.
		while cxn:
			c = cxn.pop()
			if c.isValid:
				return c
			else:
				c.close()
		return await Connection.Make(target, idle=idle or self.idle)

	def put(self, connection: Connection) -> None:
		"""Put the connection back into the pool, it will be available
		as long as it is valid."""
		self.connections.setdefault(connection.target, []).append(connection)

	def clean(self: ConnectionPoolT) -> ConnectionPoolT:
		"""Cleans idle connections by closing them and removing them
		from available connections."""
		to_remove = []
		for k in [_ for _ in self.connections]:
			cl = self.connections[k]
			for c in cl:
				if not c.isValid:
					to_remove.append(c)
			while to_remove:
				c = to_remove.pop()
				cl.remove(c)
			if not cl:
				del self.connections[k]
		return self

	def release(self: ConnectionPoolT) -> ConnectionPoolT:
		"""Releases all the connections registered"""
		for cl in self.connections.values():
			while cl:
				cl.pop().close()
		self.connections.clear()
		return self

	def pop(self: ConnectionPoolT) -> ConnectionPoolT:
		"""Pops this pool from the connection pool context and release
		all its connections."""
		pools = ConnectionPool.All.get(None)
		if pools and self in pools:
			pools.remove(self)
		self.release()
		return self

	def __enter__(self: ConnectionPoolT) -> ConnectionPoolT:
		return self

	def __exit__(self, type: Any, value: Any, traceback: Any) -> None:
		"""The connection pool automatically cleans when used
		as a context manager."""
		self.clean()


# -----------------------------------------------------------------------------
#
# HTTP CLIENT
#
# -----------------------------------------------------------------------------


class ClientException(Exception):
	def __init__(self, status: HTTPProcessingStatus):
		super().__init__(f"Client response processing failed: {status}")
		self.status = status


class HTTPClient:
	@classmethod
	async def OnRequest(
		cls,
		request: HTTPRequest,
		host: str,
		cxn: Connection,
		*,
		timeout: Union[float, None] = 2.0,
		buffer: int = 32_000,
		streaming: Union[bool, None] = None,
		keepalive: bool = False,
	) -> AsyncGenerator[HTTPAtom, Union[bool, None]]:
		"""Low level function to process HTTP requests with the given connection."""
		# We send the line
		line = f"{request.method} {request.path} HTTP/1.1\r\n".encode()
		head: dict[str, str] = request.headers
		if "Host" not in head:
			head["Host"] = host
		body = request._body
		if not streaming and "Content-Length" not in head:
			head["Content-Length"] = (
				"0"
				if body is None
				else (
					str(body.length)
					if isinstance(body, HTTPBodyBlob) or isinstance(body, HTTPBodyFile)
					else str(body.expected or "0")
				)
			)
		if "Connection" not in head:
			head["Connection"] = "keep-alive" if keepalive else "close"
		cxn.writer.write(line)
		payload = "\r\n".join(f"{k}: {v}" for k, v in head.items()).encode("ascii")
		cxn.writer.write(payload)
		cxn.writer.write(b"\r\n\r\n")
		await cxn.writer.drain()
		# NOTE: This is a common logic shared with the server
		# And send the request
		if isinstance(body, HTTPBodyBlob):
			cxn.writer.write(body.payload)
		elif isinstance(body, HTTPBodyFile):
			fd: int = -1
			try:
				fd = os.open(str(body.path), os.O_RDONLY)
				while True:
					chunk = os.read(fd, 64_000)
					if chunk:
						cxn.writer.write(chunk)
					else:
						break
			finally:
				if fd > 0:
					os.close(fd)
		elif isinstance(body, HTTPBodyStream):
			# No keep alive with streaming as these are long
			# lived requests.
			for chunk in body.stream:
				cxn.writer.write(asWritable(chunk))
				await cxn.writer.drain()
		elif isinstance(body, HTTPBodyAsyncStream):
			# No keep alive with streaming as these are long
			# lived requests.
			async for chunk in body.stream:
				cxn.writer.write(asWritable(chunk))
				await cxn.writer.drain()
		elif body is None:
			pass
		else:
			raise ValueError(f"Unsupported body format: {body}")

		iteration: int = 0
		# --
		# We continue reading from the socket if we have keep_alive
		status: HTTPProcessingStatus = HTTPProcessingStatus.Processing
		read_count: int = 0
		# --
		# We may have more than one request in each payload when
		# HTTP Pipelining is on.
		res: Union[HTTPResponse, None] = None
		while status is HTTPProcessingStatus.Processing and res is None:
			try:
				chunk = await asyncio.wait_for(
					cxn.reader.read(buffer),
					timeout=timeout,
				)
				read_count += len(chunk)
			except TimeoutError:
				raise ClientException(HTTPProcessingStatus.Timeout)
			if not chunk:
				raise ClientException(HTTPProcessingStatus.NoData)
			# NOTE: With HTTP Pipelining, we may receive more than one
			# request in the same payload, so we need to be prepared
			# to answer more than one request.
			stream = cxn.parser.feed(chunk)
			while True:
				try:
					atom = next(stream)
				except StopIteration:
					status = HTTPProcessingStatus.Complete
					break
				if atom is HTTPProcessingStatus.Complete:
					status = atom
				elif isinstance(atom, HTTPResponse):
					if atom.body:
						yield atom.body
					res = atom
					break
				else:
					yield atom
			iteration += 1
		if (
			# We continue if we have streaming or
			status is HTTPProcessingStatus.Processing
			or streaming is True
			or (res and res.body and HTTPBody.HasRemaining(res.body))
			or (res and res.headers.contentType in {"text/event-stream"})
		):
			# TODO: We should swap out the body for a streaming body
			cxn.isStreaming = True
			should_continue: Union[bool, None] = True
			while should_continue is not False:
				try:
					chunk = await asyncio.wait_for(
						cxn.reader.read(buffer),
						timeout=timeout,
					)
					if not chunk:
						break
					else:
						# We stream body blobs
						should_continue = yield HTTPBodyBlob(chunk, len(chunk))
					read_count += len(chunk)
				except TimeoutError:
					raise ClientException(HTTPProcessingStatus.Timeout)

		# We always finish with the response if we have one
		if res is not None:
			yield res

	@classmethod
	async def Request(
		cls,
		method: str,
		host: str,
		path: str,
		*,
		port: Union[int, None] = None,
		headers: Union[dict[str, str], None] = None,
		body: Union[HTTPBodyIO, HTTPBodyBlob, bytes, None] = None,
		params: Union[dict[str, str], str, None] = None,
		ssl: bool = True,
		verified: bool = True,
		timeout: float = 10.0,
		follow: bool = True,
		proxy: Union[tuple[str, int], bool, None] = None,
		connection: Union[Connection, None] = None,
		streaming: Union[bool, None] = None,
		keepalive: bool = False,
	) -> AsyncGenerator[HTTPAtom, None]:
		"""Somewhat high level API to perform an HTTP request."""

		# There's much work to get proxy support to work
		actual_port = port if port else 443 if ssl else 80
		proxy_host: Union[str, None] = None
		proxy_port: Union[int, None] = None

		# Detects if a proxy has been specified in environment variables, and configures the connection accordingly
		if proxy is True or proxy is None:
			if env_proxy := os.environ.get("HTTPS_PROXY" if ssl else "HTTP_PROXY"):
				proxy_url = urlparse(env_proxy)
				proxy_host = proxy_url.hostname
				proxy_port = int(proxy_url.port) if proxy_url.port is not None else None
		elif proxy:
			proxy_host, proxy_port = proxy

		# TODO: We may want to capture timeout as part of the target
		target: ConnectionTarget = ConnectionTarget.Make(
			host=host,
			port=port,
			ssl=ssl,
			proxy=proxy_host,
			proxyPort=proxy_port,
			verified=verified,
		)

		# We try to use the given connection, but if it's not compatible
		# we'll get a new one.
		cxn: Connection = (
			connection
			if connection and connection.target == target
			else await ConnectionPool.Connect(target, timeout=timeout)
		)

		# We expand the path to support
		if not params:
			pass
		elif isinstance(params, dict):
			p = "&".join(
				(
					f"{k}={quote_plus(v)}"
					if not isinstance(v, list)
					else "&".join(f"{k}={quote_plus(value)}" for value in v)
				)
				for k, v in params.items()
			)
			path = f"{path}&{p}" if path else p
		else:
			path = f"{path}&{params}"

		# If we have a proxy setup
		if proxy_host and proxy_port:
			if ssl:
				# We set the tunnel for HTTPS connection
				# SEE: https://devdocs.io/python~3.12/library/http.client#http.client.HTTPConnection.set_tunnel
				# SEE: https://datatracker.ietf.org/doc/html/rfc7231#section-4.3.6
				raise NotImplementedError
			else:
				# Or adjust the path for HTTP connections
				path = f"http://{host}:{actual_port}{path}"

		try:
			async for atom in cls.OnRequest(
				HTTPRequest(
					method,
					path,
					query=None,
					headers=HTTPHeaders(headers or {}),
					body=HTTPBodyBlob.FromBytes(body)
					if isinstance(body, bytes)
					else body,
				),
				host,
				cxn,
				timeout=timeout,
				streaming=streaming,
				keepalive=keepalive,
			):
				yield atom
		finally:
			# FIXME: That's a bit of an issue as the request may be streaming,
			# and so the connection should only be released when the request
			# parsing has ended, so probably not here.
			ConnectionPool.Release(cxn)


@contextmanager
def pooling(idle: Union[float, int, None] = None) -> Iterator[ConnectionPool]:
	"""Creates a context in which connections will be pooled."""
	pool = ConnectionPool().Push(idle=idle)
	try:
		yield pool
	finally:
		pool.pop().release()


async def request(
	method: str,
	host: str,
	path: str,
	*,
	port: Union[int, None] = None,
	headers: Union[dict[str, str], None] = None,
	body: Union[HTTPBodyIO, HTTPBodyBlob, None] = None,
	params: Union[dict[str, str], str, None] = None,
	ssl: bool = True,
	verified: bool = True,
	timeout: float = 10.0,
	follow: bool = True,
	proxy: Union[tuple[str, int], bool, None] = None,
	connection: Union[Connection, None] = None,
	streaming: Union[bool, None] = None,
	keepalive: bool = False,
) -> AsyncGenerator[HTTPAtom, None]:
	async for atom in HTTPClient.Request(
		method,
		host,
		path,
		port=port,
		headers=headers,
		body=body,
		params=params,
		ssl=ssl,
		verified=verified,
		follow=follow,
		proxy=proxy,
		connection=connection,
		streaming=streaming,
		keepalive=keepalive,
	):
		yield atom


if __name__ == "__main__":

	async def main() -> None:
		async for atom in HTTPClient.Request(
			host="google.com",
			method="GET",
			path="/index.html",
		):
			event("atom", atom)

	asyncio.run(main())


# EOF
