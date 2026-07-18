import asyncio
import socket
import threading
from dataclasses import dataclass
from pathlib import Path
from signal import SIGINT, SIGTERM
from typing import Any, Callable, Coroutine, Literal, NamedTuple, Union

from .config import HOST, LOG_REQUESTS, PORT
from .http.model import (
	HTTPBodyBlob,
	HTTPBodyLimitError,
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
from .utils.logging import configure as configureLogging
from .utils.logging import debug, event, exception, info, logged, warning, error


@dataclass
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
	maxBodyBytes: int = 64 * 1024 * 1024
	# NOTE: Make sure this matches the ALB configuration,
	# «The target closed the connection with a TCP RST or a TCP FIN while the load
	# balancer had an outstanding request to the target. Check whether the
	# keep-alive duration of the target is shorter than the idle timeout value of
	# the load balancer.»
	# SEE: https://repost.aws/questions/QU-_rSWDtwSmOD5wBO5tsrwg/load-balancer-502-bad-gateway
	keepalive: float = 3_600
	logRequests: bool = LOG_REQUESTS
	condition: Union[Callable[[], bool], None] = None
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
SERVER_BAD_REQUEST: bytes = (
	b"HTTP/1.1 400 Bad Request\r\n"
	b"Content-Type: text/plain\r\n"
	b"Content-Length: 11\r\n"
	b"Connection: close\r\n"
	b"\r\n"
	b"Bad Request"
)
SERVER_PAYLOAD_TOO_LARGE: bytes = (
	b"HTTP/1.1 413 Payload Too Large\r\n"
	b"Content-Type: text/plain\r\n"
	b"Content-Length: 17\r\n"
	b"Connection: close\r\n"
	b"\r\n"
	b"Payload Too Large"
)


class AIOSocketBodyReader(HTTPBodyReader):
	"""Specialized body reader to work with AIO sockets."""

	# NOTE: no __slots__ — mypyc-compiled parents reject slotted pure subclasses

	def __init__(
		self,
		socket: "socket.socket",
		loop: asyncio.AbstractEventLoop,
		size: int = 64_000,
		*,
		transform: Union[BytesTransform, None] = None,
	) -> None:
		super().__init__(transform)
		self.socket = socket
		self.loop = loop
		self.size: int = size

	async def _read(
		self, timeout: float | None = 1.0, size: Union[int, None] = None
	) -> Union[bytes, None]:
		logged(debug) and debug(
			"Reading Body",
			Client=f"{id(self.socket):x}",
			Size=size or self.size,
			Timeout=timeout if timeout is not None else "none",
		)
		if timeout is None:
			return await self.loop.sock_recv(self.socket, size or self.size)
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
		transform: Union[BytesTransform, None] = None,
	) -> None:
		super().__init__(transform)
		self.client: socket.socket = client
		self.loop: asyncio.AbstractEventLoop = loop
		# Reused across responses on this connection (avoid per-response alloc).
		self._wireBuf: bytearray = bytearray()

	async def writeResponse(self, response: HTTPResponse) -> bool:
		"""Render blob responses into a reused buffer and send once."""
		body = response.body
		if isinstance(body, HTTPBodyBlob):
			buf = self._wireBuf
			buf.clear()
			response.renderInto(buf, withBody=True)
			await self.loop.sock_sendall(self.client, buf)
			return False
		await self.write(response.head())
		await self.write(body)
		return False

	async def _writeBytes(
		self, chunk: Union[bytes, None, Literal[False]], more: bool = False
	) -> bool:
		if chunk is None or chunk is False:
			pass
		else:
			await self.loop.sock_sendall(self.client, chunk)
		return False

	async def _writeFile(
		self,
		path: Path,
		start: int | None = None,
		end: int | None = None,
		size: int = 64_000,
	) -> bool:
		with open(path, "rb") as f:
			if start is not None and end is not None:
				# Partial file: use offset and count with sendfile
				count = end - start + 1
				await self.loop.sock_sendfile(self.client, f, offset=start, count=count)
			else:
				# Full file
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
		idle_handle: Union[asyncio.TimerHandle, None] = None
		try:
			# TODO: Should reuse parser, reader, writer as these will be on the
			# hotpath for requests. These should all be recyclable.
			parser: HTTPParser = HTTPParser(requestsOnly=True)
			reader: AIOSocketBodyReader = AIOSocketBodyReader(client, loop)
			writer: AIOSocketBodyWriter = AIOSocketBodyWriter(client, loop)
			# Cache once per connection — log level rarely changes mid-flight.
			do_debug: bool = logged(debug)

			def _cancel_idle() -> None:
				nonlocal idle_handle
				if idle_handle is not None:
					idle_handle.cancel()
					idle_handle = None

			def _on_idle_timeout() -> None:
				"""Wake a blocked sock_recv by shutting down the socket."""
				nonlocal status, idle_handle
				idle_handle = None
				status = HTTPProcessingStatus.Timeout
				try:
					client.shutdown(socket.SHUT_RDWR)
				except OSError:
					pass

			# Keep-alive idle timeout strategy:
			# - Busy path: bare sock_recv_into (no wait_for, no per-read timer).
			# - Idle path: after each completed request we arm a single
			#   call_later; it is cancelled when the next bytes arrive.
			#   For very long keepalive values the timer almost never fires,
			#   but create/cancel still costs — so we only arm when the
			#   configured timeout is in a practical range (< 1 hour default
			#   still arms; set keepalive<=0 to disable).
			arm_idle: bool = 0.0 < keep_alive_timeout < 3600.0
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
				req: Union[HTTPRequest, None] = None
				# --
				# We may have more than one request in each payload when
				# HTTP Pipelining is on.
				try:
					if arm_idle and req_count > 0:
						idle_handle = loop.call_later(
							keep_alive_timeout, _on_idle_timeout
						)
					n = await loop.sock_recv_into(client, buffer)
					_cancel_idle()
					read_count += n
				except OSError:
					_cancel_idle()
					if status is HTTPProcessingStatus.Timeout:
						warning(
							"Client timed out",
							Requests=req_count,
							Responses=res_count,
						)
						break
					raise
				if not n:
					# A no-data means a close (or idle timeout shutdown)
					if status is not HTTPProcessingStatus.Timeout:
						status = HTTPProcessingStatus.NoData
					else:
						warning(
							"Client timed out",
							Requests=req_count,
							Responses=res_count,
						)
					# We need to break here as otherwise we'll be in a hot loop.
					break
				# NOTE: With HTTP Pipelining, we may receive more than one
				# request in the same payload, so we need to be prepared
				# to answer more than one request.
				# One copy of the received prefix only (not the full prealloc buffer)
				data = bytes(memoryview(buffer)[:n])
				if do_debug:
					debug(
						"Reading Requests(s)",
						Client=f"{id(client):x}",
						Read=n,
						Iteration=iteration,
						Count=req_count,
					)
				for atom in parser.feed(data):
					if atom is HTTPProcessingStatus.Complete:
						status = atom
					elif atom is HTTPProcessingStatus.BadFormat:
						status = atom
						warning(
							"Bad HTTP request format",
							Client=f"{id(client):x}",
							Iteration=iteration,
						)
						await writer.write(SERVER_BAD_REQUEST)
						res_count += 1
						keep_alive = False
						break
					elif isinstance(atom, HTTPRequest):
						req = atom
						cl = req.contentLength
						if cl is not None and cl > options.maxBodyBytes:
							await writer.write(SERVER_PAYLOAD_TOO_LARGE)
							res_count += 1
							keep_alive = False
							break
						# Attach reader only when more body may remain
						body = req._body
						if isinstance(body, HTTPBodyBlob):
							if body.remaining:
								req._reader = reader
								reader.setLimit(
									options.maxBodyBytes, alreadyRead=body.length
								)
						else:
							req._reader = reader
							reader.setLimit(options.maxBodyBytes, alreadyRead=0)
						if options.logRequests:
							event(req.method, req.path)
						req_count += 1
						# headers dict uses Kebab-Case keys from the parser
						hdrs = req._headers.headers
						if (
							req.protocol == "HTTP/1.0"
							or hdrs.get("Connection") == "close"
						):
							keep_alive = False
						res = await cls.SendResponse(req, app, writer)
						if res:
							res_count += 1
							if res.shouldClose:
								keep_alive = False
						else:
							warning(
								"Sending Response Failed",
								Iteration=iteration,
								Count=res_count,
							)
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
			if idle_handle is not None:
				idle_handle.cancel()
			# NOTE: The above loop takes care of keep alive, so we always close
			# the connection on exit.
			client.close()

	@staticmethod
	async def SendResponse(
		request: HTTPRequest,
		app: Application,
		writer: HTTPBodyWriter,
	) -> Union[HTTPResponse, None]:
		"""Processes the request within the application and sends a response using the given writer."""
		req: HTTPRequest = request
		res: Union[HTTPResponse, None] = None
		sent: bool = False
		# --
		# We process the response from the application
		r: Union[HTTPResponse, Coroutine[Any, HTTPResponse, Any]] = app.process(req)
		# Sync handlers return HTTPResponse directly (no coroutine overhead)
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
				# AIOSocketBodyWriter: render into reused buffer → one sendall
				if isinstance(writer, AIOSocketBodyWriter):
					await writer.writeResponse(res)
				else:
					body = res.body
					if isinstance(body, HTTPBodyBlob):
						await writer.write(res.wire())
					else:
						await writer.write(res.head())
						await writer.write(body)
				sent = True
			except BrokenPipeError:
				# Client did an early close
				sent = True
			except HTTPBodyLimitError:
				await writer.write(SERVER_PAYLOAD_TOO_LARGE)
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
		if options.logRequests:
			# Request events must not wait for a potentially slow stderr consumer.
			configureLogging(asynchronous=True)
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
	*components: Union[Application, Service],
	host: str = HOST,
	port: int = PORT,
	backlog: int = OPTIONS.backlog,
	condition: Union[Callable[[], bool], None] = None,
	timeout: float = OPTIONS.timeout,
	polling: float = OPTIONS.polling,
	logRequests: bool = OPTIONS.logRequests,
	keepalive: float = OPTIONS.keepalive,
	maxBodyBytes: int = OPTIONS.maxBodyBytes,
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
		maxBodyBytes=maxBodyBytes,
	)
	app = mount(*components)
	try:
		asyncio.run(AIOSocketServer.Serve(app, options))
	except KeyboardInterrupt:
		event("ManualShutdown")
	event("EOK")


# EOF
