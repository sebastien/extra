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
        self._headers[name] = [1, [value]]
        return value

    def add(self, name: str, value: Any) -> Any:
        if name not in self._headers:
            return self.set(name, value)
        else:
            v = self._headers[name]
            v[0] += 1
            v[1].append(value)
            return value


class RequestStatus(Enum):
    Initialized = 0
    Open = 1
    Closed = 3


class Request(Flyweight):

    # @group Request attributes

    def __init__(self):
        Flyweight.__init__(self)
        self.status: RequestStatus = RequestStatus.Initialized
        self._onClose: Optional[Callable[[Request], None]] = None

    def reset(self):
        super().reset()
        self.status: RequestStatus = RequestStatus.Initialized
        self._onClose = None

    @property
    def isOpen(self):
        return self.status == RequestStatus.Open

    @property
    def isClosed(self):
        return self.status == RequestStatus.Closed

    def open(self):
        self.status = RequestStatus.Open
        return self

    def close(self):
        if self.status != RequestStatus.closed:
            self.status = RequestStatus.closed
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

    def notAuthorized(self):
        pass

    def notModified(self):
        pass

    def fail(self):
        pass


BodyType = Enum("BodyType", "none value iterator")
Body = NamedTuple(
    "Body", [("type", BodyType), ("content", Union[bytes]), ("contentType", bytes)]
)


class ResponseStatus(Enum):
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
        self.status: ResponseStatus = ResponseStatus.Initialized
        self.bodies: list[TBody] = []

    def init(self, status: ResponseStatus):
        self.status = status
        return self

    @property
    def isEmpty(self):
        return not self.bodies

    def reset(self):
        self.status = ResponseStatus.Initialized
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

    @property
    def stream(self) -> Iterator[Union[ResponseControl, bytes]]:
        for content, type in self.bodies:
            yield ResponseControl.Type
            yield type
            yield ResponseControl.Chunk
            yield content
        yield ResponseControl.End


# EOF
