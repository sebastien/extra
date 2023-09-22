from typing import (
    Any,
    Callable,
    Optional,
    Iterable,
    Iterator,
    ItemsView,
    Union,
    TypeVar,
    NamedTuple,
    AsyncIterator,
    Self,
)
from types import GeneratorType
from collections.abc import Iterator as IteratorType
from ..utils import Flyweight
from enum import Enum

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
    def FromItems(self, items: Iterable[tuple[bytes, bytes]]) -> "Headers":
        headers = Headers()
        for k, v in items:
            headers._headers[k] = [v]
        return headers

    def __init__(self) -> None:
        # FIXME: Not sure why there is a list of bytes for the headers
        # seems really overkill. That should probably be a tuple.
        self._headers: dict[bytes, list[bytes]] = {}

    def reset(self) -> None:
        self._headers.clear()

    def items(self) -> ItemsView[bytes, list[bytes]]:
        return self._headers.items()

    def get(self, name: bytes) -> Optional[Union[bytes, list[bytes]]]:
        if name in self._headers:
            value = self._headers[name]
            return value[0] if len(value) == 1 else value
        else:
            return None

    def set(self, name: bytes, value: bytes) -> bytes:
        self._headers[name] = [value]
        return value

    def update(self, headers: dict[bytes, bytes]):
        for k, v in headers.items():
            self._headers[k] = [v]
        return self

    def has(self, name: bytes) -> bool:
        return name in self._headers

    def add(self, name: bytes, value: Any) -> Any:
        if name not in self._headers:
            return self.set(name, value)
        else:
            self._headers[name].append(value)
            return value


class RequestStep(Enum):
    Initialized = 0
    Open = 1
    Closed = 3


class Request(Flyweight):

    # @group Request attributes

    def __init__(self) -> None:
        Flyweight.__init__(self)
        self.step: RequestStep = RequestStep.Initialized
        self._onClose: Optional[Callable[[Request], None]] = None

    def reset(self) -> None:
        super().reset()
        self.step = RequestStep.Initialized
        self._onClose = None

    @property
    def isOpen(self) -> bool:
        return self.step == RequestStep.Open

    @property
    def isClosed(self) -> bool:
        return self.step == RequestStep.Closed

    # NOTE: Not sure why we need these
    def open(self) -> "Request":
        self.step = RequestStep.Open
        return self

    def close(self) -> "Request":
        if self.step != RequestStep.Closed:
            self.step = RequestStep.Closed
            if self._onClose:
                self._onClose(self)
        return self

    def onClose(self, callback: Optional[Callable[["Request"], None]]) -> "Request":
        self._onClose = callback
        return self

    @property
    def uri(self) -> str:
        raise NotImplementedError

    # @group Params

    # @property
    # def params(self):
    #     pass

    # def getParam(self, name: str) -> Any:
    #     pass

    # @group Loading

    # @property
    # def isLoaded(self):
    #     pass

    # @property
    # def loadProgress(self):
    #     pass

    # def load(self) -> Any:
    #     pass

    # @group Files

    # @property
    # def files(self):
    #     pass

    # def getFile(self, name: str) -> Any:
    #     pass

    # @group Responses
    # def multiple(self):
    #     pass

    # def bounce(self):
    #     pass

    # def stream(self):
    #     pass

    # def local(self):
    #     pass

    # # @group Errors
    # def notFound(self):
    #     pass

    # def notAuthorized(self, messase: Optional[str] = None):
    #     pass

    # def notModified(self):
    #     pass

    # def fail(self):
    #     pass


class ResponseBodyType(Enum):
    Empty = b"empty"
    Value = b"value"
    Stream = b"iterator"
    AsyncStream = b"asyncStream"


class ResponseBody(NamedTuple):
    type: ResponseBodyType
    content: Union[bytes, Iterator[bytes], AsyncIterator[bytes]]
    contentType: bytes


class ResponseStep(Enum):
    Initialized = 0
    Ready = 1
    Sent = 2


# TODO: The response should have ways to stream the bodies and write
# them to different formats.


class ResponseControl(Enum):
    Chunk = 0
    Type = 1
    End = 2


class Response(Flyweight):
    def __init__(self) -> None:
        Flyweight.__init__(self)
        self.step: ResponseStep = ResponseStep.Initialized
        self.bodies: list[ResponseBody] = []
        # FIXME: I don't really like the headers like this
        self.headers: Optional[Headers] = Headers()
        self.status: int = 0

    def init(
        self,
        *,
        step: ResponseStep = ResponseStep.Initialized,
        bodies: Optional[list[ResponseBody]] = None,
        headers: Optional[Headers] = None,
        status: int = 0,
    ) -> Self:
        self.step = step
        self.bodies = [] if bodies is None else bodies
        self.headers = headers
        self.status = status
        return self

    @property
    def isEmpty(self) -> bool:
        return not self.bodies

    def reset(self):
        self.step = ResponseStep.Initialized
        self.bodies.clear()
        return self

    def setCookie(self, name: bytes, value: bytes) -> "Response":
        raise NotImplementedError

    def setHeader(self, name: bytes, value: bytes) -> "Response":
        raise NotImplementedError

    def setHeaders(self, headers: Optional[dict[bytes, bytes]]):
        if headers:
            if not self.headers:
                self.headers = Headers()
            self.headers.update(headers)
        return self

    def setContent(
        self,
        content: Union[str, bytes, Any],
        contentType: Optional[Union[str, bytes]] = None,
    ) -> "Response":
        if isinstance(
            content, str
        ):  # SEE: https://www.w3.org/International/articles/http-charset/index
            self.bodies.append(
                ResponseBody(
                    ResponseBodyType.Value,
                    asBytes(content),
                    asBytes(contentType or b"text/plain; charset=utf-8"),
                )
            )
        elif isinstance(content, bytes):
            self.bodies.append(
                ResponseBody(
                    ResponseBodyType.Value,
                    content,
                    asBytes(contentType or b"application/binary"),
                )
            )
        elif isinstance(content, IteratorType) or isinstance(content, GeneratorType):
            self.bodies.append(
                ResponseBody(
                    ResponseBodyType.Stream,
                    content,
                    asBytes(contentType or b"application/binary"),
                )
            )
        else:
            if not contentType:
                raise ValueError(
                    "contentType must be specified when type is not bytes or str"
                )
            self.bodies.append(
                ResponseBody(ResponseBodyType.Value, content, asBytes(contentType))
            )
        return self

    def addStream(self, stream: Iterator[bytes], contentType: Union[str, bytes]):
        if not contentType:
            raise ValueError(
                "contentType must be specified when type is not bytes or str"
            )
        self.bodies.append(
            ResponseBody(ResponseBodyType.Stream, stream, asBytes(contentType))
        )
        return self

    def stream(self) -> Iterator[Union[ResponseControl, bytes]]:
        for body in self.bodies:
            yield ResponseControl.Type
            yield body.type.value
            content = body.content
            if content is None:
                pass
            elif isinstance(content, bytes):
                yield ResponseControl.Chunk
                yield content
            else:
                raise ValueError(f"Unsupported body value: {content}")
        yield ResponseControl.End


# EOF
