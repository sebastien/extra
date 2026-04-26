from typing import Any, TypeAlias, cast
import json as basejson
from .primitives import asPrimitive

try:
	import orjson as _orjson
except ImportError:
	_orjson = None  # type: ignore[assignment]

# TODO: We do want to use ORJSON when available: https://github.com/tktech/json_benchmark

TJSON: TypeAlias = None | int | float | bool | list[Any] | dict[str, Any]

# Primitive types that don't need asPrimitive conversion
PRIMITIVE_TYPES: set[type] = {type(None), bool, int, float, str}


def isPrimitive(value: Any) -> bool:
	"""Checks whether value is already JSON-serialisable without conversion."""
	if type(value) in PRIMITIVE_TYPES:
		return True
	elif isinstance(value, dict):
		return all(isinstance(k, str) and isPrimitive(v) for k, v in value.items())
	elif isinstance(value, (list, tuple)):
		return all(isPrimitive(v) for v in value)
	return False


def json(value: Any) -> bytes:
	"""Converts a value to JSON bytes."""
	if _orjson is not None:
		# orjson handles common types natively and returns bytes directly.
		# Only fall back to asPrimitive for complex types (dataclasses,
		# named tuples, etc.) that orjson can't serialise.
		try:
			return _orjson.dumps(value)
		except TypeError:
			return _orjson.dumps(asPrimitive(value))
	else:
		# stdlib json: skip asPrimitive when value is already primitive
		if isPrimitive(value):
			return basejson.dumps(value).encode("utf8")
		return basejson.dumps(asPrimitive(value)).encode("utf8")


def unjson(value: bytes | str) -> TJSON:
	"""Converts JSON-encoded to a string."""
	if _orjson is not None:
		return cast(TJSON, _orjson.loads(value))
	return cast(TJSON, basejson.loads(value))


# EOF
