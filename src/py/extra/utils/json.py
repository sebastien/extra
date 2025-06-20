from typing import Any, TypeAlias, cast
import json as basejson
from .primitives import asPrimitive


# TODO: We do want to use ORJSON when available: https://github.com/tktech/json_benchmark

TJSON: TypeAlias = None | int | float | bool | list[Any] | dict[str, Any]


def json(value: Any) -> bytes:
	"""Converts JSON to a string."""
	return basejson.dumps(asPrimitive(value)).encode("utf8")


def unjson(value: bytes | str) -> TJSON:
	"""Converts JSON-encoded to a string."""
	return cast(TJSON, basejson.loads(value))


# EOF
