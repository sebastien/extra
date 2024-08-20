from typing import NamedTuple, ClassVar
from .http.model import (
    HTTPRequest,
    HTTPRequestHeaders,
    HTTPRequestBody,
    HTTPRequestBlob,
    headername,
)
import asyncio, ssl, time, os
from urllib.parse import quote_plus, urlparse
from contextvars import ContextVar
from contextlib import contextmanager
from dataclasses import dataclass

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
    proxy: Target | None = None
    verified: bool = True

    @staticmethod
    def Make(
        host: str,
        port: int | None = None,
        ssl: bool = True,
        *,
        timeout: float | None = None,
        proxy: str | None = None,
        proxyPort: int | None = None,
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


@dataclass(slots=True)
class Connection:
    """Wraps an underlying HTTP(S) connection with its target
    information."""

    target: ConnectionTarget
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    idle: float
    until: float | None

    def close(self):
        """Closes the writer."""
        self.writer.close()
        self.until = None
        return self

    @property
    def isValid(self) -> bool | None:
        """Tells if the connection is still valid."""
        return (time.monotonic() <= self.until) if self.until else None

    def touch(self):
        """Touches the connection, bumping its `until` time."""
        self.until = time.monotonic() + self.idle
        return self

    @staticmethod
    async def Make(
        target: ConnectionTarget,
        *,
        timeout: float | None = None,
        idle: float | None,
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
            target, reader, writer, idle=idle, until=time.monotonic() + idle
        )


class ConnectionPool:
    """Context-aware pool of connections."""

    All: ClassVar[ContextVar] = ContextVar("httpConnectionsPool")

    @classmethod
    def Get(cls, *, idle: float | None = None) -> "ConnectionPool":
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
        idle: float | None = None,
        timeout: float | None = None,
        verified: bool = True,
    ) -> Connection:
        """Returns a connection to the target from the pool (if the pool is available
        and has a valid connection to the target), or creates a new connection."""
        pools = cls.All.get(None)
        return (
            pools[-1].get(target)
            if pools
            else await Connection.Make(
                target, idle=idle, timeout=timeout, verified=verified
            )
        )

    @classmethod
    def Release(cls, connection: Connection) -> bool:
        """Releases the connection back into the pool. If the connection
        is invalid, it will be closed instead."""
        pools = cls.All.get(None)
        # TODO: Should we close the underling connection or not?
        # connection.underlying.close()
        if not connection.isValid:
            return False
        elif pools:
            connection.close()
            pools[-1].put(connection)
            return True
        else:
            connection.close()
            return False

    @classmethod
    def Push(cls, *, idle: float | None = None) -> "ConnectionPool":
        pools = cls.All.get(None)
        if pools is None:
            pools = []
            cls.All.set(pools)
        pool = ConnectionPool(idle=idle)
        pools.append(pool)
        return pool

    @classmethod
    def Pop(cls):
        pools = cls.All.get(None)
        if pools:
            pools.pop().release()

    def __init__(self, idle: float | None = None):
        self.connections: dict[ConnectionTarget, list[Connection]] = {}
        self.idle: float | None = idle

    def get(
        self,
        target: ConnectionTarget,
        *,
        idle: float | None = None,
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
        return Connection.Make(target, idle=idle or self.idle)

    def put(self, connection: Connection) -> None:
        """Put the connection back into the pool, it will be available
        as long as it is valid."""
        self.connections.setdefault(connection.target, []).append(connection)

    def clean(self):
        """Cleans idle connections by closing them and removing them
        from available connections."""
        to_remove = []
        for k in [_ for _ in self.connections]:
            l = self.connections[k]
            for c in l:
                if not c.isValid:
                    to_remove.append(c)
            while to_remove:
                c = to_remove.pop()
                l.remove(c)
            if not l:
                del self.connections[k]
        return self

    def release(self):
        """Releases all the connections registered"""
        for l in self.connections.values():
            while l:
                l.pop().close()
        self.connections.clear()

    def pop(self):
        """Pops this pool from the connection pool context and release
        all its connections."""
        pools = ConnectionPool.All.get(None)
        if pools and self in pools:
            pools.remove(self)
        self.release()
        return self

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        """The connection pool automatically cleans when used
        as a context manager."""
        self.clean()


# -----------------------------------------------------------------------------
#
# HTTP CLIENT
#
# -----------------------------------------------------------------------------


class AIOSocketClient:

    @classmethod
    async def OnRequest(
        cls,
        request: HTTPRequest,
        host: str,
        cxn: Connection,
        *,
        headers: dict[str, str] | None = None,
        body: HTTPRequestBody | HTTPRequestBlob | None = None,
    ):
        """Low level function to process HTTP requests with the given connection."""
        # We send the line
        line = f"{request.method} {request.path} HTTP/1.1\r\n".encode()
        # We send the headers
        head: dict[str, str] = (
            {headername(k): v for k, v in headers.items()} if headers else {}
        )
        if "Host" not in head:
            head["Host"] = host
        # if "Content-Length" not in head:
        #     head["Content-Length"] = "0"
        if "Connection" not in head:
            head["Connection"] = "close"
        cxn.writer.write(line)
        payload = "\r\n".join(f"{k}: {v}" for k, v in head.items()).encode("ascii")
        cxn.writer.write(payload)
        cxn.writer.write(b"\r\n\r\n")
        await cxn.writer.drain()
        # TODO: Write the body
        res = await cxn.reader.read()
        return res

    @classmethod
    async def Request(
        cls,
        method: str,
        host: str,
        path: str,
        *,
        port: int | None = None,
        headers: dict[str, str] | None = None,
        body: HTTPRequestBody | HTTPRequestBlob | None = None,
        params: dict[str, str] | str | None = None,
        ssl: bool = True,
        verified: bool = True,
        timeout: float | None = 10.0,
        follow: bool = True,
        proxy: tuple[str, int] | bool | None = None,
        connection: Connection | None = None,
    ):
        """Somewhat high level API to perform an HTTP request."""

        # There's much work to get proxy support to work
        actual_port = port if port else 443 if ssl else 80
        proxy_host: str | None = None
        proxy_port: int | None = None

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
            res = await cls.OnRequest(
                HTTPRequest(
                    method, path, query=None, headers=HTTPRequestHeaders(headers)
                ),
                host,
                cxn,
            )
            return res
        finally:
            ConnectionPool.Release(cxn)


@contextmanager
def pooling(idle: float | None = None):
    """Creates a context in which connections will be pooled."""
    pool = ConnectionPool().Push(idle=idle)
    try:
        yield pool
    finally:
        pool.pop()


if __name__ == "__main__":
    res = asyncio.run(
        AIOSocketClient.Request(
            host="google.com",
            method="GET",
            path="/index.html",
        )
    )


# EOF
