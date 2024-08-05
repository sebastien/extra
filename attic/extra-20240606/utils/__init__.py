from abc import ABC, abstractmethod
from typing import Generic, TypeVar, ClassVar, cast

T = TypeVar("T", bound="Flyweight")


class Flyweight(ABC, Generic[T]):
    Pool: ClassVar[list["Flyweight"]] = []
    Capacity: ClassVar[int] = 1_000

    @classmethod
    def Recycle(cls, value: T) -> None:
        if len(cls.Pool) >= cls.Capacity:
            return None
        cls.Pool.append(value)

    @classmethod
    def Create(cls) -> T:
        return cast(T, cls.Pool.pop() if cls.Pool else cls())

    def init(self) -> T:
        return self.reset()

    @abstractmethod
    def reset(self) -> T:
        ...

    def recycle(self) -> None:
        self.reset()
        self.__class__.Pool.append(cast(T, self))


def unquote(text: bytes) -> bytes:
    text = text.strip() if text else text
    if not text:
        return text
    if text[0] == text[-1] and text[0] in b"\"'":
        return text[1:-1]
    else:
        return text


# EOF
