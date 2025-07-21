import asyncio
import socket
import threading
from dataclasses import dataclass
from pathlib import Path
from signal import SIGINT, SIGTERM
from typing import Any, Callable, Coroutine, Literal, NamedTuple

from .config import HOST, PORT
from .http.model import (
	HTTPBodyReader,
	HTTPBodyWriter,
	HTTPProcessingStatus,
	HTTPRequest,
	HTTPResponse,
)
from .http.parser import HTTPParser
from .model import Application, Service, mount
from .utils.codec import BytesTransform
from .utils.limits import LimitType, unlimit
from .utils.logging import debug, event, exception, info, logged, warning, error


@dataclass(slots=True)
class ServerState:
	isRunning: bool = True

	def stop(self) -> None:
		info("Server stopping…")
		self.isRunning = False

	def onException(
		self, loop: asyncio.AbstractEventLoop, context: dict[str, Any]
	) -> None:
		e = context.get("exception")
		if e:
			exception(e)


class ServerOptions(NamedTuple):
	host: str = "0.0.0.0"  # nosec: B104
	port: int = 8000
	backlog: int = 10_000
	timeout: float = 10.0
	# This is the polling timeout for accepting new requests. Every second is
	# good
	polling: float = 1.0
	readsize: int = 4_096
	# NOTE: Make sure this matches the ALB configuration,
	# «The target closed the connection with a TCP RST or a TCP FIN while the load
	# balancer had an outstanding request to the target. Check whether the
	# keep-alive duration of the target is shorter than the idle timeout value of
	# the load balancer.»
	# SEE: https://repost.aws/questions/QU-_rSWDtwSmOD5wBO5tsrwg/load-balancer-502-bad-gateway
	keepalive: float = 3_600
	logRequests: bool = True
	condition: Callable[[], bool] | None = None
	stopSignals: bool = True


OPTIONS: ServerOptions = ServerOptions()

SERVER_OK: bytes = (
	b"HTTP/1.1 200 OK\r\n"
	b"Content-Type: text/plain\r\n"
	b"Content-Length: 2\r\n"
	b"Connection: close\r\n"
	b"\r\n"
	b"OK\r\n"
)

SERVER_NOCONTENT: bytes = b"HTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n"
SERVER_ERROR: bytes = (
	b"HTTP/1.1 500 Internal Server Error\r\n"
	b"Content-Type: text/plain\r\n"
	b"Content-Length: 39\r\n"
	b"Connection: close\r\n"
	b"\r\n"
	b"Internal server error: Request not sent\r\n"
)


class AIOSocketBodyReader(HTTPBodyReader):
	"""Specialized body reader to work with AIO sockets."""

	__slots__ = ["socket", "loop", "buffer", "size"]

	def __init__(
		self,
		socket: "socket.socket",
		loop: asyncio.AbstractEventLoop,
		size: int = 64_000,
		*,
		transform: BytesTransform | None = None,
	) -> None:
		super().__init__(transform)
		self.socket = socket
		self.loop = loop
		self.size: int = size

	async def _read(
		self, timeout: float = 1.0, size: int | None = None
	) -> bytes | None:
		logged(debug) and debug(
			"Reading Body",
			Client=f"{id(self.socket):x}",
			Size=size or self.size,
			Timeout=timeout,
		)
		return await asyncio.wait_for(
			self.loop.sock_recv(self.socket, size or self.size),
			timeout=timeout,
		)


class AIOSocketBodyWriter(HTTPBodyWriter):
	"""Specialized body writer to work with AIO sockets."""

	def __init__(
		self,
		client: "socket.socket",
		loop: asyncio.AbstractEventLoop,
		*,
		transform: BytesTransform | None = None,
	) -> None:
		super().__init__(transform)
		self.client: socket.socket = client
		self.loop: asyncio.AbstractEventLoop = loop

	async def _writeBytes(
		self, chunk: bytes | None | Literal[False], more: bool = False
	) -> bool:
		if chunk is None or chunk is False:
			pass
		else:
			await self.loop.sock_sendall(self.client, chunk)
		return False

	async def _writeFile(self, path: Path, size: int = 64_000) -> bool:
		with open(path, "rb") as f:
			await self.loop.sock_sendfile(self.client, f)
		return True


# NOTE: Based on benchmarks, this gave the best performance.
# NOTE: The caveat is that getting SSL directly is a pain, so we may
# need to rewrite this a bit.
class AIOSocketServer:
	"""AsyncIO backend using sockets directly."""

	@classmethod
	async def OnRequest(
		cls,
		app: Application,
		client: socket.socket,
		*,
		loop: asyncio.AbstractEventLoop,
		options: ServerOptions,
	) -> None:
		"""Asynchronous worker, processing a socket in the context
		of an application."""
		size: int = options.readsize
		# TODO: Support keep-alive
		# TODO: We should loop and leave the connection open if we're
		# in keep-alive mode.
		buffer = bytearray(size)
		# NOTE: Keepalive timeout should be relative to the time it takes
		# to process a request, and to the backlog size as well.
		keep_alive_timeout: float = options.keepalive
		keep_alive: bool = True
		iteration: int = 0
		# --
		# We continue reading from the socket if we have keep_alive
		status: HTTPProcessingStatus = HTTPProcessingStatus.Processing
		read_count: int = 0
		res_count: int = 0
		req_count: int = 0
		try:
			# TODO: Should reuse parser, reader, writer as these will be on the
			# hotpath for requests. These should all be recyclable.
			parser: HTTPParser = HTTPParser()
			reader: AIOSocketBodyReader = AIOSocketBodyReader(client, loop)
			writer: AIOSocketBodyWriter = AIOSocketBodyWriter(client, loop)

			# NOTE: Here a load balancer will sustain a single connection and
			# all the requests will come through this loop, until there's
			# Connection: Close, or the keepalive timeout has expired.
			# --
			# SEE: https://repost.aws/knowledge-center/apache-backend-elb
			# TODO: We should manage the Keep-Alive header
			# Keep-Alive: timeout=5, max=1000
			# --
			# NOTE: The response can notify through StreamControl if the
			# connection should be closed. When it is, we proceed. This
			# typically happen when there's an underlying error with
			# a response that returns a stream.
			while keep_alive and not writer.shouldClose:
				req: HTTPRequest | None = None
				# --
				# We may have more than one request in each payload when
				# HTTP Pipelining is on.
				try:
					# NOTE: The timeout really doesn't do anything here, the
					# socket will return no data, instead of being blocking
					n = await asyncio.wait_for(
						loop.sock_recv_into(client, buffer),
						timeout=keep_alive_timeout,
					)
					read_count += n
				except TimeoutError:
					warning("Client timed out", Requests=req_count, Responses=res_count)
					status = HTTPProcessingStatus.Timeout
					break
				if not n:
					# A no-data means a close
					status = HTTPProcessingStatus.NoData
					# We need to break here as otherwise we'll be in a hot loop.
					break
				# NOTE: With HTTP Pipelining, we may receive more than one
				# request in the same payload, so we need to be prepared
				# to answer more than one request.
				chunk = buffer[:n] if n != size else buffer
				# TODO: We're converting a bytearray to bytes, check if that's performant.
				stream = parser.feed(bytes(chunk))
				debug(
					"Reading Requests(s)",
					Client=f"{id(client):x}",
					Read=n,
					Iteration=iteration,
					Count=req_count,
				)
				while True:
					try:
						atom = next(stream)
						debug("Request Atom", Atom=atom.__class__.__name__)
					except StopIteration:
						# TODO: Should be debug
						debug("Requests End", Iteration=iteration, Count=res_count)
						break
					if atom is HTTPProcessingStatus.Complete:
						status = atom
					elif isinstance(atom, HTTPRequest):
						req = atom
						# We pass the reader to the request, as for instance
						# the request may need more than what was available
						# from the socket.
						req._reader = reader
						# Logs the request method
						if options.logRequests:
							event(req.method, req.path)
						req_count += 1
						if (
							req.protocol == "HTTP/1.0"
							or req.headers.get("Connection") == "close"
						):
							keep_alive = False
						res = await cls.SendResponse(req, app, writer)
						if res:
							res_count += 1
							info("Request Sent", Iteration=iteration, Count=res_count)
							if res.shouldClose:
								info("Response wants to close connection")
								keep_alive = False
						else:
							warning(
								"Sending Response Failed",
								Iteration=iteration,
								Count=res_count,
							)
				# We clear what we've read from the buffer
				if n != size:
					del buffer[:n]
				else:
					# FIXME: Or is it buffer.clear()?
					del buffer[:]
				iteration += 1

			# NOTE: We'll need to think about the loading of the body, which
			# should really be based on content length. It may be in memory,
			# it may be spooled, or it may be streamed. There should be some
			# update system as well.
			if res_count != req_count:
				warning("Incomplete responses", Requests=req_count, Responses=res_count)
			if not read_count:
				if req_count == 0:
					# This is a regular connection close
					pass
				else:
					# TODO: We should extract the client IP
					warning(
						"Client did not send any data",
						ReadCount=read_count,
						Status=status.name,
						Requests=req_count,
						Responses=res_count,
					)
			elif status is HTTPProcessingStatus.NoData and not res_count:
				# TODO: We should extract the client IP
				warning(
					"Client did not feed a complete request",
					ReadCount=read_count,
					Status=status.name,
					Requests=req_count,
					Responses=res_count,
				)
			elif status is HTTPProcessingStatus.Timeout:
				if not req_count or req_count != res_count:
					# TODO: We should extract the client IP
					warning(
						"Client timed out",
						ReadCount=read_count,
						Status=status.name,
						Requests=req_count,
						Responses=res_count,
					)
				else:
					# That's a normal timeout due to keep alive
					pass
			else:
				pass

		except Exception as e:
			exception(e)
		finally:
			# NOTE: The above loop takes care of keep alive, so we always close
			# the connection on exit.
			client.close()

	@staticmethod
	async def SendResponse(
		request: HTTPRequest,
		app: Application,
		writer: HTTPBodyWriter,
	) -> HTTPResponse | None:
		"""Processes the request within the application and sends a response using the given writer."""
		req: HTTPRequest = request
		res: HTTPResponse | None = None
		sent: bool = False
		# --
		# We process the response from the application
		r: HTTPResponse | Coroutine[Any, HTTPResponse, Any] = app.process(req)
		if isinstance(r, HTTPResponse):
			res = r
		else:
			res = await r
		if res is None:
			warning(
				"Application did not return a response",
				Method=req.method,
				Path=req.path,
			)
			await writer.write(SERVER_NOCONTENT)
			sent = True
		else:
			try:
				# We send the request head
				await writer.write(res.head())
				sent = True
				await writer.write(res.body)
			except BrokenPipeError:
				# Client did an early close
				sent = True
			except Exception as e:
				exception(e)
		if req._onClose:
			try:
				req._onClose(req)
			except Exception as e:
				# NOTE: close handler failed
				exception(e)
		if res and res._onClose:
			try:
				res._onClose(res)
			except Exception as e:
				# NOTE: close handler failed
				exception(e)
		if req and not sent:
			try:
				warning(
					"Server did not send a response",
					Method=req.method,
					Path=req.path,
				)
				await writer.write(SERVER_ERROR)
			except Exception as e:
				exception(e)
				# TODO: Should close?

		return res

	@classmethod
	async def Serve(
		cls,
		app: Application,
		options: ServerOptions = ServerOptions(),
	) -> None:
		"""Main server coroutine."""
		server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		server.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
		port: int = options.port
		try:
			server.bind((options.host, port))
		except OSError as e:
			warning(f"Could not bind to {options.host}:{port}, trying other ports.")
			bound: bool = False
			for p in range(options.port + 1, options.port + 5):
				try:
					server.bind((options.host, p))
					bound = True
					port = p
					info(f"Found alternate available port: {port}")
				except OSError:
					pass
			if not bound:
				error(
					f"Unable to bind to {options.host}:{options.port}, aborting.",
					"HOSTPORTERR",
				)
				raise e from e

		# The argument is the backlog of connections that will be accepted before
		# they are refused.
		server.listen(options.backlog)
		# This is what we need to use it with asyncio
		server.setblocking(False)

		tasks: set[asyncio.Task[None]] = set()
		try:
			loop = asyncio.get_running_loop()
		except RuntimeError:
			loop = asyncio.new_event_loop()

		# Manage server state
		state = ServerState()
		# Registers handlers for signals and exception (so that we log them). Note
		# that we'll get a `set_wakeup_fd only works in main thread of the main interpreter`
		# when this is not run out of the main thread.
		if (
			options.stopSignals
			and threading.current_thread() is threading.main_thread()
		):
			loop.add_signal_handler(SIGINT, lambda: state.stop())
			loop.add_signal_handler(SIGTERM, lambda: state.stop())
		loop.set_exception_handler(state.onException)

		info(
			"Extra AIO Server listening",
			icon="🚀",
			Host=options.host,
			Port=port,
		)

		try:
			while state.isRunning:
				if options.condition and not options.condition():
					break
				try:
					res = await asyncio.wait_for(
						loop.sock_accept(server), timeout=options.polling or 1.0
					)
					if res is None:
						continue
					else:
						client = res[0]
					# NOTE: Should do something with the tasks
					task = loop.create_task(
						cls.OnRequest(app, client, loop=loop, options=options)
					)
					tasks.add(task)
					task.add_done_callback(tasks.discard)
				except asyncio.TimeoutError:
					continue
				except OSError as e:
					# This can be: [OSError] [Errno 24] Too many open files
					if e.errno == 24:
						# Implement backpressure or wait mechanism here
						await asyncio.sleep(0.1)  # Short delay before retrying
					else:
						exception(e)

		finally:
			server.close()
			for task in tasks:
				task.cancel()
			await asyncio.gather(*tasks, return_exceptions=True)


def run(
	*components: Application | Service,
	host: str = HOST,
	port: int = PORT,
	backlog: int = OPTIONS.backlog,
	condition: Callable[[], bool] | None = None,
	timeout: float = OPTIONS.timeout,
	polling: float = OPTIONS.polling,
	logRequests: bool = OPTIONS.logRequests,
	keepalive: float = OPTIONS.keepalive,
) -> None:
	"""High level function to run the server."""
	unlimit(LimitType.Files)
	options = ServerOptions(
		host=host,
		port=port,
		backlog=backlog,
		condition=condition,
		timeout=timeout,
		polling=polling,
		logRequests=logRequests,
		keepalive=keepalive,
	)
	app = mount(*components)
	try:
		asyncio.run(AIOSocketServer.Serve(app, options))
	except KeyboardInterrupt:
		event("ManualShutdown")
	event("EOK")


# EOF
