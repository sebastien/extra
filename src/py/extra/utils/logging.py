import sys
import time
import inspect
import atexit
import os
import threading
from queue import Queue, Empty
from enum import Enum
from typing import NamedTuple, Any, TypeAlias
from contextvars import ContextVar
from .primitives import TPrimitive
from .term import Term

ERR = sys.stderr


LogOrigin: ContextVar[str] = ContextVar("LogOrigin", default="extra")
LogSpan: ContextVar[str | int | None] = ContextVar("LogSpan", default=None)


class LogType(Enum):
	Message = 0  # A general information message
	Metric = 10  # A data point/metric
	Event = 20  # An event
	Audit = 30  # An audit information (must keep)


class LogLevel(Enum):
	Debug = 0
	Info = 10
	Checkpoint = 20
	Warning = 30  # A Warning
	Error = 40  # A managed error
	Exception = 50  # An un-managed error
	Alert = 60  # Alerts need to be relayed
	Critical = 70  # Critical needs to be relayed


LOG_LEVEL_COLOR = {
	LogLevel.Debug: 31,
	LogLevel.Info: 75,
	LogLevel.Checkpoint: 81,
	LogLevel.Warning: 202,
	LogLevel.Error: 160,
	LogLevel.Exception: 124,
	LogLevel.Alert: 89,
	LogLevel.Critical: 163,
}

LOG_LEVEL_NAMES: dict[str, LogLevel] = {
	"debug": LogLevel.Debug,
	"info": LogLevel.Info,
	"checkpoint": LogLevel.Checkpoint,
	"warning": LogLevel.Warning,
	"error": LogLevel.Error,
	"exception": LogLevel.Exception,
	"alert": LogLevel.Alert,
	"critical": LogLevel.Critical,
}

_CURRENT_LOG_LEVEL: LogLevel = LogLevel.Info


class LogEntry(NamedTuple):
	origin: str
	time: float
	type: LogType = LogType.Message
	level: LogLevel = LogLevel.Info
	message: str | None = None
	name: str | None = None
	value: TPrimitive | None = None
	context: dict[str, TPrimitive] | None = None
	icon: str | None = None
	stack: list[str] | None = None


TStack: TypeAlias = list[str]


def callstack(offset: int = 1) -> list[str]:
	"""
	Returns a list of function/method names on the call stack.
	For methods, the class name is included as 'ClassName.methodName'.
	"""
	return [
		(
			f"{_.frame.f_locals['self'].__class__.__qualname__}.{_.function}"
			if "self" in _.frame.f_locals
			else (
				f"{_.frame.f_locals['cls'].__class__.__qualname__}.{_.function}"
				if "cls" in _.frame.f_locals
				else _.function
			)
		).replace("<lambda>", "λ")
		for _ in reversed(inspect.stack()[offset:])
	]


def formatData(value: Any) -> str:
	if value is None or value == () or value == [] or value == {}:
		return "◌"
	elif isinstance(value, dict):
		# TODO: We should make the key brighter/bolder
		return " ".join(
			f"{Term.BOLD}{k}{Term.NORMAL}={formatData(v)}" for k, v in value.items()
		)
	elif isinstance(value, list) or isinstance(value, tuple):
		return ",".join(formatData(v) for v in value)
	elif isinstance(value, str):
		return repr(value) if " " in value else value
	elif isinstance(value, bool):
		return "✓" if value else "✗"
	elif isinstance(value, float):
		return f"{value:0.2f}"
	else:
		return str(value)


def _render(entry: LogEntry) -> tuple[str, str | None]:
	icon: str = f" {entry.icon}" if entry.icon else ""
	clr: str = Term.Color(LOG_LEVEL_COLOR[entry.level])
	if entry.type == LogType.Event:
		line = (
			f"{clr}{Term.BOLD}[{entry.origin}] {entry.name}{Term.RESET} "
			f"{formatData(entry.value)} {formatData(entry.context)}{Term.RESET}\n"
		)
	else:
		line = (
			f"{clr}{Term.BOLD}[{entry.origin}]{Term.RESET}{icon} "
			f"{entry.message} {formatData(entry.context)}{Term.RESET}\n"
		)
	stack_line = (
		f"{clr}{Term.Color(38)}  {' ' * len(entry.origin)} {'→'.join(entry.stack)}{Term.RESET}\n"
		if entry.stack
		else None
	)
	return line, stack_line


class LoggerSink:
	def send(self, entry: LogEntry) -> LogEntry:
		raise NotImplementedError

	def close(self) -> None:
		pass


class SyncLogger(LoggerSink):
	def send(self, entry: LogEntry) -> LogEntry:
		line, stack_line = _render(entry)
		ERR.write(line)
		if stack_line is not None:
			ERR.write(stack_line)
		ERR.flush()
		return entry


class AsyncLogger(LoggerSink):
	def __init__(self) -> None:
		self._queue: Queue[str] = Queue()
		self._stop: threading.Event = threading.Event()
		self._worker: threading.Thread = threading.Thread(
			target=self._run,
			name="extra-log-worker",
			daemon=True,
		)
		self._worker.start()

	def _drain(self) -> None:
		while True:
			try:
				line = self._queue.get_nowait()
			except Empty:
				break
			ERR.write(line)
		ERR.flush()

	def _run(self) -> None:
		while not self._stop.is_set():
			try:
				line = self._queue.get(timeout=0.25)
			except Empty:
				continue
			ERR.write(line)
			# Keep logger de-prioritized vs request path by batching flushes.
			if self._queue.empty():
				ERR.flush()
				time.sleep(0.001)
		self._drain()

	def send(self, entry: LogEntry) -> LogEntry:
		line, stack_line = _render(entry)
		self._queue.put(line)
		if stack_line is not None:
			self._queue.put(stack_line)
		return entry

	def close(self) -> None:
		self._stop.set()
		self._worker.join(timeout=1.0)
		self._drain()


class Logger:
	def __init__(self, sink: LoggerSink | None = None) -> None:
		self._sink: LoggerSink = sink if sink is not None else SyncLogger()

	def configure(self, *, asynchronous: bool = False) -> None:
		if asynchronous:
			if isinstance(self._sink, AsyncLogger):
				return
			self._sink.close()
			self._sink = AsyncLogger()
		else:
			if isinstance(self._sink, SyncLogger):
				return
			self._sink.close()
			self._sink = SyncLogger()

	def shutdown(self) -> None:
		self.configure(asynchronous=False)

	def send(self, entry: LogEntry) -> LogEntry:
		return self._sink.send(entry)


DEFAULT_LOGGER = Logger()


def configure(*, asynchronous: bool = False) -> None:
	"""Configures logging backend.

	When `asynchronous=True`, log lines are queued and written by a background
	worker thread so request processing does not block on stderr I/O.
	"""
	DEFAULT_LOGGER.configure(asynchronous=asynchronous)


def shutdown() -> None:
	"""Flushes queued logs and stops the async worker if enabled."""
	DEFAULT_LOGGER.shutdown()


def send(entry: LogEntry) -> LogEntry:
	if entry.level.value >= _CURRENT_LOG_LEVEL.value:
		return DEFAULT_LOGGER.send(entry)
	return entry


def setLevel(level: LogLevel) -> LogLevel:
	global _CURRENT_LOG_LEVEL
	previous = _CURRENT_LOG_LEVEL
	_CURRENT_LOG_LEVEL = level
	return previous


def getLevel() -> LogLevel:
	return _CURRENT_LOG_LEVEL


def entry(
	*,
	origin: str | None = None,
	at: float | None = None,
	type: LogType = LogType.Message,
	level: LogLevel = LogLevel.Info,
	message: str | None = None,
	name: str | None = None,
	value: TPrimitive | None = None,
	context: dict[str, TPrimitive],
	icon: str | None = None,
	stack: TStack | bool | None = None,
) -> LogEntry:
	return LogEntry(
		origin=origin or LogOrigin.get(),
		time=time.time() if at is None else at,
		type=type,
		level=level,
		message=message,
		name=name,
		value=value,
		context=context,
		icon=icon,
		stack=callstack(1) if stack is True else stack if stack else None,
	)


def debug(
	message: str,
	*,
	origin: str | None = None,
	at: float | None = None,
	icon: str | None = None,
	stack: TStack | bool | None = None,
	**context: TPrimitive,
) -> LogEntry:
	return send(
		entry(
			message=message,
			level=LogLevel.Debug,
			origin=origin,
			at=at,
			context=context,
			icon=icon,
			stack=callstack(1) if stack is True else stack if stack else None,
		)
	)


def info(
	message: str,
	*,
	origin: str | None = None,
	at: float | None = None,
	icon: str | None = None,
	stack: TStack | bool | None = None,
	**context: TPrimitive,
) -> LogEntry:
	return send(
		entry(
			message=message,
			origin=origin,
			at=at,
			context=context,
			icon=icon,
			stack=callstack(1) if stack is True else stack if stack else None,
		)
	)


def warning(
	message: str,
	*,
	origin: str | None = None,
	at: float | None = None,
	icon: str | None = None,
	stack: TStack | bool | None = None,
	**context: TPrimitive,
) -> LogEntry:
	return send(
		entry(
			message=message,
			level=LogLevel.Warning,
			origin=origin,
			at=at,
			context=context,
			icon=icon,
			stack=callstack(1) if stack is True else stack if stack else None,
		)
	)


def error(
	message: str,
	code: int | str | None,
	*,
	origin: str | None = None,
	at: float | None = None,
	icon: str | None = None,
	stack: TStack | bool | None = None,
	**context: TPrimitive,
) -> LogEntry:
	return send(
		entry(
			message=message,
			value=code,
			level=LogLevel.Error,
			origin=origin,
			at=at,
			context=context,
			icon=icon,
			stack=callstack(1) if stack is True else stack if stack else None,
		)
	)


def event(
	event: str,
	value: Any = None,
	*,
	origin: str | None = None,
	at: float | None = None,
	stack: TStack | bool | None = None,
	**context: TPrimitive,
) -> LogEntry:
	return send(
		entry(
			name=event,
			value=value,
			type=LogType.Event,
			origin=origin,
			at=at,
			context=context,
			stack=callstack(1) if stack is True else stack if stack else None,
		)
	)


def notify(
	name: str,
	value: Any = None,
	*,
	origin: str | None = None,
	at: float | None = None,
	stack: TStack | bool | None = None,
) -> LogEntry:
	return event(
		event=name,
		value=value,
		origin=origin,
		at=at,
		stack=callstack(2) if stack is True else stack if stack else None,
	)


def exception(
	exception: Exception,
	message: str | None = None,
	# origin: str | None = None,
) -> Exception:
	try:
		stream = ERR
		stream.write(
			f"!!! EXCP {f'{message}: [{exception.__class__.__name__}] {exception}' if message else f'[{exception.__class__.__name__}] {exception}'}\n"
		)
		tb = exception.__traceback__
		while tb:
			code = tb.tb_frame.f_code
			stream.write(
				f"... in {code.co_name:15s} at {tb.tb_lineno:4d} in {code.co_filename}\n",
			)
			tb = tb.tb_next
		stream.flush()
	except Exception:  # nosec: B110
		# Swallow all exceptions so that this function can be called from an exception
		# handler safely, such as in the implementation of logging/logging sinks.
		pass

	# Return the exception so that this function can be called like:
	#   raise onException(exception)
	return exception


def logged(item: Any) -> bool:
	"""Takes one of the logging function, and tells if it is currently
	supported. This is used to guard against running the whole entry
	building when not necessary."""
	if item is debug:
		level = LogLevel.Debug
	elif item is info or item is event:
		level = LogLevel.Info
	elif item is warning:
		level = LogLevel.Warning
	elif item is error:
		level = LogLevel.Error
	elif item is exception:
		level = LogLevel.Exception
	else:
		return True
	return level.value >= _CURRENT_LOG_LEVEL.value


atexit.register(shutdown)

# Optional opt-in from environment:
#   EXTRA_ASYNC_LOGS=1|true|yes|on
if os.getenv("EXTRA_ASYNC_LOGS", "").strip().lower() in ("1", "true", "yes", "on"):
	configure(asynchronous=True)


if level := os.getenv("EXTRA_LOG_LEVEL", "").strip().lower():
	if parsed := LOG_LEVEL_NAMES.get(level):
		setLevel(parsed)
	else:
		warning(
			"Invalid EXTRA_LOG_LEVEL value, keeping default",
			Value=level,
			Default=getLevel().name.lower(),
		)


# EOF
