import asyncio
import threading
from typing import Generic, Optional, TypeVar

T = TypeVar("T")


class Channel(Generic[T]):
	def __init__(self) -> None:
		self._buffer: list[tuple[T, threading.Event]] = []
		self._condition = threading.Condition()
		self._isOpen = False

	@property
	def isOpen(self) -> bool:
		return self._isOpen

	def open(self) -> "Channel[T]":
		with self._condition:
			self._isOpen = True
		return self

	def close(self) -> "Channel[T]":
		with self._condition:
			self._isOpen = False
			self._condition.notify_all()
		return self

	def push(self, value: T) -> T:
		with self._condition:
			if not self._isOpen:
				return value
			self._buffer.append((value, threading.Event()))
			self._condition.notify()
		return value

	def consume(self, timeout: Optional[float] = None) -> Optional[T]:
		"""Wait for and remove the next value, or return ``None`` on timeout."""
		with self._condition:
			if not self._wait(timeout):
				return None
			value, consumed = self._buffer.pop(0)
			consumed.set()
			return value

	def peek(self) -> T:
		with self._condition:
			if self._buffer:
				return self._buffer[0][0]
			raise ValueError("Channel is empty")

	def has(self) -> bool:
		with self._condition:
			return bool(self._buffer)

	def _wait(self, timeout: Optional[float]) -> bool:
		if self._buffer:
			return True
		if not self._isOpen:
			return False
		return self._condition.wait_for(
			lambda: bool(self._buffer) or not self._isOpen,
			timeout,
		) and bool(self._buffer)

	async def join(self, timeout: Optional[float] = None) -> Optional[T]:
		"""Waits for a value to come in."""
		loop = asyncio.get_running_loop()
		return await loop.run_in_executor(None, self._join, timeout)

	def _join(self, timeout: Optional[float]) -> Optional[T]:
		with self._condition:
			if not self._wait(timeout):
				return None
			return self._buffer[0][0]

	async def pushwait(
		self, value: T, timeout: Optional[float] = None
	) -> bool:
		"""Push a value and wait until that value is consumed."""
		with self._condition:
			if not self._isOpen:
				return False
			consumed = threading.Event()
			self._buffer.append((value, consumed))
			self._condition.notify()

		loop = asyncio.get_running_loop()
		return await loop.run_in_executor(None, consumed.wait, timeout)


# NOTE: MypyC does not support async gen
#  async def consume(channel: Channel):
#      yield None


# EOF
