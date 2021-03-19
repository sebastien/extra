from typing import TypeVar, Generic, List

T = TypeVar('T')


class Channel(Generic[T]):

    def __init__(self):
        self._buffer: List[T] = []
        self._isOpen = False

    @property
    def isOpen(self) -> bool:
        return self._isOpen

    def open(self) -> 'Channel':
        self._isOpen = True
        return self

    def close(self) -> 'Channel':
        self._isOpen = False
        return self

    def push(self, value: T) -> T:
        self._buffer.append(value)

    def consume(self) -> T:
        if self._buffer:
            return self._buffer.pop(0)
        else:
            raise ValueError("Channel is empty")

    def peek(self) -> T:
        if self._buffer:
            return self._buffer[0]
        else:
            raise ValueError("Channel is empty")

    def has(self) -> bool:
        return bool(self._buffer)

    async def join(self) -> T:
        """Waits for a value to come in."""
        return None


async def consume(channel: Channel):
    yield None

# EOF
