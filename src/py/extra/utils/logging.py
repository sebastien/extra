import sys, time
from enum import Enum
from typing import NamedTuple, Any
from contextvars import ContextVar
from .primitives import TPrimitive

ERR = sys.stderr


LogOrigin: ContextVar[str] = ContextVar("LogOrigin", default="extra")
LogSpan: ContextVar[str | int | None] = ContextVar("LogSpan", default=None)


class LogType(Enum):
    Message = 0
    Event = 10


class LogLevel(Enum):
    Critical = 60  # Critical needs to be relayed
    Alert = 50  # Alerts need to be relayed
    Audit = 40  # Audits need to be kept, always
    Error = 30
    Warning = 20
    Info = 10
    Debug = 0


class LogEntry(NamedTuple):
    origin: str
    time: float
    type: LogType = LogType.Message
    level: LogLevel = LogLevel.Info
    message: str | None = None
    name: str | None = None
    value: TPrimitive | None = None


def send(entry: LogEntry) -> LogEntry:
    ERR.write(f"[{entry.origin}] {entry.message}\n")
    ERR.flush()
    return entry


def info(
    message: str, *, origin: str | None = None, at: float | None = None
) -> LogEntry:
    return send(
        LogEntry(
            message=message,
            origin=origin or LogOrigin.get(),
            time=time.time() if at is None else at,
        )
    )


def error(
    message: str,
    code: int | str | None,
    *,
    origin: str | None = None,
    at: float | None = None,
) -> LogEntry:
    return send(
        LogEntry(
            message=message,
            value=code,
            level=LogLevel.Error,
            origin=origin or LogOrigin.get(),
            time=time.time() if at is None else at,
        )
    )


def notify(
    event: str, value: Any, *, origin: str | None = None, at: float | None = None
) -> LogEntry:
    return send(
        LogEntry(
            name=event,
            value=value,
            type=LogType.Event,
            origin=origin or LogOrigin.get(),
            time=time.time() if at is None else at,
        )
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


# EOF
