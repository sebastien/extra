from typing import NamedTuple
from .server import AIOSocketReader
from .http.model import (
    HTTPRequest,
    HTTPRequestHeaders,
    HTTPRequestBody,
    HTTPRequestBlob,
    headername,
)
import asyncio, socket, os, ssl


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


class ClientOptions(NamedTuple):
    pass


class AIOSocketClient:

    @classmethod
    async def OnRequest(
        cls,
        request: HTTPRequest,
        host: str,
        reader,
        writer,
        *,
        loop: asyncio.AbstractEventLoop,
        options: ClientOptions,
        headers: dict[str, str] | None = None,
        body: HTTPRequestBody | HTTPRequestBlob | None = None,
    ):
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
        writer.write(line)
        payload = "\r\n".join(f"{k}: {v}" for k, v in head.items()).encode("ascii")
        writer.write(payload)
        writer.write(b"\r\n\r\n")
        await writer.drain()
        res = await reader.read()
        return res

    @classmethod
    async def Request(
        cls,
        *,
        host: str,
        port: int = 443,
        method: str,
        path: str,
        loop: asyncio.AbstractEventLoop,
        headers: dict[str, str] | None = None,
        body: HTTPRequestBody | HTTPRequestBlob | None = None,
        # TODO: Support a connection pool
        options: ClientOptions | None = None,
        hostname: str = os.environ.get("HOSTNAME", "localhost"),
        ssl: bool = True,
    ):
        if ssl:
            reader, writer = await asyncio.open_connection(
                host, 443, ssl=SSL_CLIENT_CONTEXT
            )
        else:
            reader, writer = await asyncio.open_connection(host, port)

        # reader, writer = await asyncio.open_connection(host, port)
        # Create a TCP socket and connect to the server
        # sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # if ssl:
        #     context = SSL_CLIENT_CONTEXT
        #     sock = context.wrap_socket(sock, server_hostname=hostname)
        # reader, writer = await asyncio.open_connection(sock=sock)
        res = await cls.OnRequest(
            HTTPRequest(method, path, query=None, headers=HTTPRequestHeaders(headers)),
            host,
            reader,
            writer,
            loop=loop,
            options=options or ClientOptions(),
        )
        writer.close()
        return res


if __name__ == "__main__":
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()

    res = asyncio.run(
        AIOSocketClient.Request(
            host="sebastienpierre.me",
            method="GET",
            path="/index.html",
            loop=loop,
        )
    )
    print(">>>", res)


# EOF
