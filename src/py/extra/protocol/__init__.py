from typing import (
    Any,
    Callable,
    Optional,
    Iterable,
    Iterator,
    Any,
    Union,
    TypeVar,
    Generic,
    NamedTuple,
    AsyncGenerator,
)
from extra.util import Flyweight
from enum import Enum
import types

T = TypeVar("T")


def asBytes(value: Union[str, bytes]) -> bytes:
    if isinstance(value, bytes):
        return value
    elif isinstance(value, str):
        return bytes(value, "utf8")
    elif value is None:
        return b""
    else:
        raise ValueError(f"Expected bytes or str, got: {value}")


class Headers:
    @classmethod
    def FromItems(self, items: Iterable[tuple[bytes, bytes]]):
        headers = Headers()
        for k, v in items:
            headers._headers[k] = [v]
        return headers

    def __init__(self):
        # FIXME: Not sure why there is a list of bytes for the headers
        # seems really overkill. That should probably be a tuple.
        self._headers: dict[bytes, list[bytes]] = {}

    def reset(self):
        self._headers.clear()

    def items(self) -> Iterable[tuple[bytes, bytes]]:
        return self._headers.items()

    def get(self, name: str) -> Any:
        if name in self._headers:
            count, value = self._headers[name]
            if count == 1:
                return value[0]
            else:
                return value

    def set(self, name: str, value: Any) -> Any:
        # FIXME: This is not even right!
        self._headers[name] = [1, [value]]
        return value

    def has(self, name: str) -> bool:
        return name in self._headers

    def add(self, name: str, value: Any) -> Any:
        if name not in self._headers:
            return self.set(name, value)
        else:
            v = self._headers[name]
            v[0] += 1
            v[1].append(value)
            return value


class RequestStep(Enum):
    Initialized = 0
    Open = 1
    Closed = 3


class Request(Flyweight):

    # @group Request attributes

    def __init__(self):
        Flyweight.__init__(self)
        self.step: RequestStep = RequestStep.Initialized
        self._onClose: Optional[Callable[[Request], None]] = None

    def reset(self):
        super().reset()
        self.step: RequestStep = RequestStep.Initialized
        self._onClose = None

    @property
    def isOpen(self):
        return self.step == RequestStep.Open

    @property
    def isClosed(self):
        return self.step == RequestStep.Closed

    def open(self):
        self.step = RequestStep.Open
        return self

    def close(self):
        if self.step != RequestStep.closed:
            self.step = RequestStep.closed
            if self._onClose:
                self._onClose(self)
        return self

    def onClose(self, callback: Optional[Callable[["Request"], None]]):
        self._onClose = callback
        return self

    @property
    def uri(self):
        pass

    # @group Params

    @property
    def params(self):
        pass

    def getParam(self, name: str) -> Any:
        pass

    # @group Loading

    @property
    def isLoaded(self):
        pass

    @property
    def loadProgress(self):
        pass

    def load(self) -> Any:
        pass

    # @group Files

    @property
    def files(self):
        pass

    def getFile(self, name: str) -> Any:
        pass

    # @group Responses
    def multiple(self):
        pass

    def redirect(self):
        pass

    def bounce(self):
        pass

    def returns(self):
        pass

    def stream(self):
        pass

    def local(self):
        pass

    # @group Errors
    def notFound(self):
        pass

    def notAuthorized(self, messase: Optional[str] = None):
        pass

    def notModified(self):
        pass

    def fail(self):
        pass


BodyType = Enum("BodyType", "none value iterator")
Body = NamedTuple(
    "Body", [("type", BodyType), ("content", Union[bytes]), ("contentType", bytes)]
)


class ResponseStep(Enum):
    Initialized = 0
    Ready = 1
    Sent = 2


TBody = tuple[Union[bytes, Iterator[bytes]], bytes]


# TODO: The response should have ways to stream the bodies and write
# them to different formats.


class ResponseControl(Enum):
    Chunk = 0
    Type = 1
    End = 2


class Response(Flyweight):
    def __init__(self):
        Flyweight.__init__(self)
        self.step: ResponseStep = ResponseStep.Initialized
        self.bodies: list[TBody] = []
        self.headers: Optional[Headers] = None
        self.status: int = 0

    def init(self, step: ResponseStep):
        self.step = step
        return self

    @property
    def isEmpty(self):
        return not self.bodies

    def reset(self):
        self.step = ResponseStep.Initialized
        self.bodies.clear()
        return self

    def setCookie(self, name: str, value: Any):
        pass

    def setHeader(self, name: str, value: Any):
        pass

    def setContent(
        self,
        content: Union[str, bytes, Any],
        contentType: Optional[Union[str, bytes]] = None,
    ) -> "Response":
        if isinstance(
            content, str
        ):  # SEE: https://www.w3.org/International/articles/http-charset/index
            self.bodies.append((asBytes(content), b"text/plain; charset=utf-8"))
        elif isinstance(content, bytes):
            self.bodies.append((content, asBytes(contentType or b"application/binary")))
        else:
            if not contentType:
                raise ValueError(
                    "contentType must be specified when type is not bytes or st"
                )
            self.bodies.append((content, asBytes(contentType)))
        return self

    async def stream(self) -> Iterator[Union[ResponseControl, bytes]]:
        for content, type in self.bodies:
            yield ResponseControl.Type
            yield type
            if content is None:
                pass
            elif isinstance(content, bytes):
                yield ResponseControl.Chunk
                yield content
            else:
                raise ValueError(f"Unsupported body value: {content}")
        yield ResponseControl.End


# EOF
