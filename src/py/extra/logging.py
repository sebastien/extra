from typing import Optional, Callable, ClassVar, Any

# from extra.feature.pubsub import pub, sub
from contextlib import contextmanager
import sys
import time
import os

# TODO: Update with proper typing
# try:
#     import colorama
#     from colorama import Fore, Back, Style
#
#     colorama.init()
# except ImportError as e:
#     colorama = None
colorama = None

__doc__ = """
A logging infrastructure that uses an underlying pub/sub bus to dispatch
messages.

The main difference between this module and more common logging systems is that
the logging functions support ad-hoc structured data that can then be captured
by the effector. This means that the logging subsystem can be used as a way
to generate metrics and events as well as generating human-readable messages.

See `Logger.Effector` for more detail.
"""


TPubSubEvent = dict[str, Any]
TPubSubHandler = Callable[[str, TPubSubEvent], Optional[bool]]

# -----------------------------------------------------------------------------
#
# MICRO PUB-SUB
#
# -----------------------------------------------------------------------------


class PubSub:
    def __init__(self) -> None:
        self.topics: dict[str, list[TPubSubHandler]] = {}

    def pub(self, topic: str, event: TPubSubEvent) -> TPubSubEvent:
        while topic:
            if topic in self.topics:
                for h in self.topics[topic]:
                    h(topic, event)
            if (i := topic.rfind(".")) >= 0:
                topic = topic[:i]
            else:
                break
        return event

    def sub(self, topic: str, handler: TPubSubHandler) -> "PubSub":
        self.topics.setdefault(topic, []).append(handler)
        return self

    def unsub(self, topic: str, handler: TPubSubHandler) -> "PubSub":
        self.topics[topic].remove(handler)
        return self


BUS = PubSub()


def pub(topic: str, **props: Any):
    BUS.pub(topic, props)


sub = BUS.sub

# -----------------------------------------------------------------------------
#
# LOGGER
#
# -----------------------------------------------------------------------------


class Logger:
    """Wraps logging methods in a `path` used to publish messages to using
    the underlying pub/sub module."""

    EFFECTOR_REGISTERED: ClassVar[bool] = False
    INSTANCE: ClassVar[Optional["Logger"]] = None
    FORMAT: ClassVar[dict[str, str]] = {
        "default": "[{origin}]   --- {message}",
        "error": "[{origin}] ✘ ERR {message}",
        "exception": "[{origin}] ‼ EXC {message}",
        "warning": "[{origin}] ! WRN {message}",
        "metric": "[{origin}] → DAT {name} = {value}",
        "info": "[{origin}] » ... {message}",
        "log": "[{origin}] ┄ --- {message}",
    }

    @classmethod
    def Instance(cls) -> "Logger":
        if not cls.INSTANCE:
            cls.INSTANCE = Logger("default")
        return cls.INSTANCE

    @classmethod
    def Effector(
        cls,
        topic: str,
        event,
        *,
        default: dict[str, str] = {
            "origin": "∅",
            "message": "∅",
            "name": "∅",
            "value": "∅",
        },
        output=sys.stderr if os.getenv("EXTRA_LOG_OUTPUT") == "stderr" else sys.stdout,
    ):
        """The effector is what actually outputs messages to the console.
        This can be monkey-patched but the better way to expand is to
        bind a handler to the pub/sub bus.

        This effector will log `error`  messages like `{key,code}` to
        `errors.tsv` and will log `metric` like `{name,value}` to
        `metrics.tsv`.
        """
        event_type = event.get(
            "type", topic.split(".", 1)[0] if "." in topic else topic
        )
        # NOTE: Unused
        # message = event.data.get("message")
        fmt = cls.FORMAT.get(event_type, cls.FORMAT["default"])
        # This is the user-friendly output.
        output.write(fmt.format(**(default | event)))
        if ctx := event.get("context"):
            for l in ctx:
                output.write(f"… {l}\n")
        output.write("\n")
        # FIXME: This should be done elsewhere
        # if event_type == "error" and "key" in event.data and "code" in event.data:
        #     # We log errors in a file for later reference
        #     exists = os.path.exists("errors.tsv")
        #     with open("errors.tsv", "at") as f:
        #         if not exists:
        #             f.write("timestamp	key	code\n")
        #         f.write(
        #             f"{time.strftime('%Y-%m-%d %H:%M:%S %z')}	{event.data['key']}	{event.data['code']}\n"
        #         )
        # if event_type == "metric":
        #     # We log metrics in a file
        #     exists = os.path.exists("metrics.tsv")
        #     with open("metrics.tsv", "at") as f:
        #         if not exists:
        #             f.write("timestamp	name	value\n")
        #         f.write(
        #             f"{time.strftime('%Y-%m-%d %H:%M:%S %z')}	{event.data['name']}	{event.data['value']}\n"
        #         )

    def __init__(self, path: str):
        self.path: str = path
        self.errors: int = 0
        self.warnings: int = 0
        self.metrics: int = 0
        self.exceptions: int = 0

    def info(self, message: str, **kwargs):
        return self.raw(message, type="info", **kwargs)

    def log(self, message: str, **kwargs):
        return self.raw(message, type="log", **kwargs)

    def trace(self, message: str, **kwargs):
        return self.raw(message, type="trace", **kwargs)

    def warning(self, message: str, **kwargs):
        self.warnings += 1
        return self.raw(message, type="warning", **kwargs)

    def error(self, code, detail, **kwargs):
        self.errors += 1
        return self.raw(
            f"{code}: {detail.format(code=code, **kwargs) if kwargs.get('format') is not False else detail}",
            type="error",
            code=code,
            detail=detail,
            **kwargs,
        )

    def metric(self, name, value, **kwargs):
        self.metrics += 1
        return self.raw(
            f"{name}={value}", type="metric", name=name, value=value, **kwargs
        )

    # TODO: This should definitely log and raise the exception
    def exception(self, exception, **kwargs):
        self.exceptions += 1
        tb = exception.__traceback__
        context: list[str] = []
        while tb:
            code = tb.tb_frame.f_code
            context.append(
                f"... in {code.co_name:15s} at {tb.tb_lineno:4d} in {code.co_filename}",
            )
            tb = tb.tb_next
        data = {"type": exception.__class__.__name__, "context": context}
        return self.raw(str(exception), **(data | kwargs))

    def raw(self, message, **kwargs):
        # We make sure that there's an effector registered
        if not Logger.EFFECTOR_REGISTERED:
            sub("logs", Logger.Effector)
            Logger.EFFECTOR_REGISTERED = True
        pub(
            f"logs.{self.path}",
            message=message,
            origin=kwargs.get("origin", self.path),
            **kwargs,
        )

    def timer(self, name):
        start = time.time()

        def timer_end(start=start, name=name):
            elapsed = time.time() - start
            self.metric(f"timer.{name}", elapsed)
            return elapsed

        return timer_end


class WithLog:
    """A trait that sets up a per-instance logger bound to the given path,
    which is using the class name by default."""

    def __init__(self, path: Optional[str] = None):
        self.log = Logger(path=path or self.__class__.__name__.lower())


def logger(path: str):
    return Logger(path)


def info(message, **kwargs):
    return Logger.Instance().info(message, **kwargs)


def log(message, **kwargs):
    return Logger.Instance().log(message, **kwargs)


def trace(message, **kwargs):
    return Logger.Instance().trace(message, **kwargs)


def warning(message, **kwargs):
    return Logger.Instance().warning(message, **kwargs)


def error(code: str, detail: str, **kwargs):
    return Logger.Instance().error(code, detail, **kwargs)


def exception(exception, **kwargs):
    return Logger.Instance().exception(exception, **kwargs)


def metric(name, value, **kwargs):
    return Logger.Instance().metric(name, value)


def raw(message, type, **kwargs):
    return Logger.Instance().raw(message, type=type, **kwargs)


@contextmanager
def operation(message: str):
    t = time.time()
    log("{message}…")
    yield None
    log(f"… finished in {time.time() - t:0.2f}s")


def timer(name):
    return Logger.Instance().timer(name)


# EOF
