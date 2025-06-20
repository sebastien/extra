from typing import TypeVar, Generator, Iterator, Any, cast
from types import GeneratorType

T = TypeVar("T")


def flatiter(
	value: T | list[T] | tuple[T, ...] | Generator[T, Any, Any],
) -> Iterator[T]:
	"""Flat iteration over the given value."""
	if (
		isinstance(value, list)
		or isinstance(value, tuple)
		or isinstance(value, GeneratorType)
	):
		for _ in value:
			yield from flatiter(_)
	else:
		yield cast(T, value)


# EOF
