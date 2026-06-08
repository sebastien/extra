#!/usr/bin/env python3

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "py"

if str(SRC) not in sys.path:
	sys.path.insert(0, str(SRC))

from extra.client import request
from extra.http.model import HTTPResponse


BODY = b"hello"


async def _serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
	buffer = bytearray()
	while b"\r\n\r\n" not in buffer:
		chunk = await reader.read(1024)
		if not chunk:
			break
		buffer += chunk
	writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\n" + BODY)
	await writer.drain()
	writer.close()
	await writer.wait_closed()


async def main() -> None:
	server = await asyncio.start_server(_serve, "127.0.0.1", 0)
	try:
		assert server.sockets is not None
		port = server.sockets[0].getsockname()[1]
		response: HTTPResponse | None = None
		async for atom in request(
			"GET",
			"127.0.0.1",
			"/",
			port=port,
			ssl=False,
			timeout=2.0,
			keepalive=False,
		):
			if isinstance(atom, HTTPResponse):
				response = atom
		assert response is not None, "Expected an HTTP response"
		assert response.status == 200, f"Unexpected status: {response.status}"
		payload = await response.body.load() if response.body else b""
		assert payload == BODY, f"Unexpected body: {payload!r}"
		print("OK! close-delimited response was read")
	finally:
		server.close()
		await server.wait_closed()


if __name__ == "__main__":
	asyncio.run(main())

# EOF
