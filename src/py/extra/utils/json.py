from typing import Any
import json as basejson
from .primitives import asPrimitive


# TODO: We do want to use ORJSON when available: https://github.com/tktech/json_benchmark

TJSON = None | int | float | bool | list | dict


def json(value: Any) -> bytes:
    """Converts JSON to a string."""
    return basejson.dumps(asPrimitive(value)).encode("utf8")


def unjson(value: bytes | str) -> TJSON:
    """Converts JSON-encoded to a string."""
    return basejson.loads(value)


# EOF
