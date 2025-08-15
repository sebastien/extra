import sys
import time
import inspect
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


def send(entry: LogEntry) -> LogEntry:
	icon: str = f" {entry.icon}" if entry.icon else ""
	clr: str = Term.Color(LOG_LEVEL_COLOR[entry.level])
	if entry.type == LogType.Event:
		ERR.write(
			f"{clr}{Term.BOLD}[{entry.origin}] {entry.name}{Term.RESET} {formatData(entry.value)} {formatData(entry.context)}{Term.RESET}\n"
		)
	else:
		ERR.write(
			f"{clr}{Term.BOLD}[{entry.origin}]{Term.RESET}{icon} {entry.message} {formatData(entry.context)}{Term.RESET}\n"
		)
	if entry.stack:
		ERR.write(
			f"{clr}{Term.Color(38)}  {' ' * len(entry.origin)} {'→'.join(entry.stack)}{Term.RESET}\n"
		)
	ERR.flush()
	return entry


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
	# TODO: Implement based on log level
	return True


# EOF
