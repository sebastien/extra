import asyncio
from typing import Callable
from enum import Enum
import socket
import os
import multiprocessing

from httpparser import HTTPParser, HTTPParserStatus

HAS_UVLOOP: bool = False

try:
	import uvloop

	HAS_UVLOOP = True
	if os.getenv("USE_UVLOOP") == "1":
		asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
	pass


class ServerOptions:
	host: str = "0.0.0.0"
	port: int = 8000
	backlog: int = 10_000
	timeout: float = 10.0
	condition: Callable[[], bool] | None = None


CANNED_RESPONSE: bytes = (
	b"HTTP/1.1 200 OK\r\n"
	b"Content-Type: text/plain\r\n"
	b"Content-Length: 13\r\n"
	b"\r\n"
	b"Hello, World!\r\n"
)


class RequestStatus(Enum):
	Processing = 1
	Complete = 2
	Timeout = 3
	NoData = 4


class AIOServer:
	__slots__ = ["options", "parsers"]

	def __init__(self, options: ServerOptions):
		self.options = options
		self.parsers: list[HTTPParser] = []

	async def request(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
		try:
			parser: HTTPParser = self.parsers.pop() if self.parsers else HTTPParser()
			size: int = 4096
			status = RequestStatus.Processing

			while status is RequestStatus.Processing:
				try:
					chunk = await asyncio.wait_for(
						reader.read(size), timeout=self.options.timeout
					)
				except TimeoutError:
					status = RequestStatus.Timeout
					break
				if not chunk:
					status = RequestStatus.NoData
					break
				for atom in parser.feed(chunk):
					if atom is HTTPParserStatus.Complete:
						status = RequestStatus.Complete
			# FIXME: We may have partial processing
			# We can tell the reader we're done here
			reader.feed_eof()
			writer.write(CANNED_RESPONSE)
			self.parsers.append(parser)
			await writer.drain()
		except Exception as e:
			print(f"Error handling request: {e}")
		finally:
			writer.close()
			await writer.wait_closed()


# NOTE: This is like aiosocketServer but uses a buffer. Does not really
# make a difference, maybe a tiny bit faster?
async def aiosocketBufServer(
	client: socket.socket,
	*,
	loop,
	options: ServerOptions,
	parsers: list[HTTPParser] = [],
):
	try:
		parser: HTTPParser = parsers.pop() if parsers else HTTPParser()
		size: int = 4096
		status = RequestStatus.Processing

		buffer = bytearray(size)
		while status is RequestStatus.Processing:
			try:
				n = await asyncio.wait_for(
					loop.sock_recv_into(client, buffer), timeout=options.timeout
				)
			except TimeoutError:
				status = RequestStatus.Timeout
				break
			if not n:
				status = RequestStatus.NoData
				break
			for atom in parser.feed(buffer[:n] if n != size else buffer):
				if atom is HTTPParserStatus.Complete:
					status = RequestStatus.Complete
		# NOTE: We can do `sock_sendfile` which is super useful for
		if (err := await loop.sock_sendall(client, CANNED_RESPONSE)) is not None:
			print("ERR", err)
	except Exception as e:
		print(f"Error handling request: {e}")
	finally:
		client.close()


async def aiosocketServer(
	client: socket.socket,
	*,
	loop,
	options: ServerOptions,
	parsers: list[HTTPParser] = [],
):
	try:
		parser: HTTPParser = parsers.pop() if parsers else HTTPParser()
		size: int = 4096
		status = RequestStatus.Processing

		while status is RequestStatus.Processing:
			try:
				chunk = await asyncio.wait_for(
					loop.sock_recv(client, size), timeout=options.timeout
				)
			except TimeoutError:
				status = RequestStatus.Timeout
				break
			if not chunk:
				status = RequestStatus.NoData
				break
			for atom in parser.feed(chunk):
				if atom is HTTPParserStatus.Complete:
					status = RequestStatus.Complete
		if (err := await loop.sock_sendall(client, CANNED_RESPONSE)) is not None:
			print("ERR", err)
	except Exception as e:
		print(f"Error handling request: {e}")
	finally:
		client.close()


async def mstrand(server, options):
	try:
		loop = asyncio.get_running_loop()
	except RuntimeError:
		loop = asyncio.new_event_loop()

	while True:
		client, _ = await loop.sock_accept(server)
		loop.create_task(aiosocketBufServer(client, loop=loop, options=options))


# NOTE: This gives me 9K RPS on Fedora 40 without uvloop. With uvloop this
# increases to 10.8K RPS.
def mrun(
	options: ServerOptions = ServerOptions(),
):
	server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
	server.bind((options.host, options.port))
	# The argument is the backlog of connections that will be accepted before
	# they are refused.
	server.listen(options.backlog)
	server.setblocking(False)
	for _ in range(5):
		p = multiprocessing.Process(
			target=lambda server, options: asyncio.run(mstrand(server, options)),
			args=(server, options),
		)
		p.daemon = True  # Allow child processes to exit with the main process
		p.start()
	import time

	while True:
		time.sleep(10)


# NOTE: This gives me 15K RPS on Fedora 40 without uvloop. With uvloop this
# drops to 7.5KRPS.
async def arun(
	options: ServerOptions = ServerOptions(),
):
	server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
	server.bind((options.host, options.port))
	# The argument is the backlog of connections that will be accepted before
	# they are refused.
	server.listen(options.backlog)
	server.setblocking(False)

	try:
		loop = asyncio.get_running_loop()
	except RuntimeError:
		loop = asyncio.new_event_loop()

	while True:
		client, _ = await loop.sock_accept(server)
		loop.create_task(aiosocketBufServer(client, loop=loop, options=options))


# NOTE: This gives me ~7-8K RPS
def run(
	options: ServerOptions = ServerOptions(),
):
	try:
		loop = asyncio.get_running_loop()
	except RuntimeError:
		loop = asyncio.new_event_loop()
	# loop.set_exception_handler(onLoopException)
	# app = mount(*components)
	# loop.run_until_complete(app.start())
	aio_server = AIOServer(options)
	# This the stock AIO processing
	coro = asyncio.start_server(
		aio_server.request, options.host, options.port, backlog=options.backlog
	)
	loop.run_until_complete(coro)
	loop.run_forever()


# --
# Findings:
# - AIO server is 4.5K RPS (expecteD)
# - AIO socket is an astounding 9.4 RPS (and I got it to 14K)
# - Multiprocessing really doesn't make a difference
# - UV loop doesn't make a difference
# - PyPy3 doesn't make a difference
#
# It's potentially still useful to switch backends, but I'd say using the
# sockets directly is a win.
if __name__ == "__main__":
	# AIO server
	# run()
	# AIO Socket
	asyncio.run(arun())
	# AIO Socket Multiprocessing
	# mrun()

# EOF
