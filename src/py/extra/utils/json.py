from typing import Any
import json as basejson


# TODO: We do want to use ORJSON when available: https://github.com/tktech/json_benchmark


def json(value: Any) -> bytes:
    """Converts JSON to a string."""
    return basejson.dumps(value).encode("utf8")


def unjson(value: bytes | str) -> Any:
    """Converts JSON-encoded to a string."""
    return basejson.loads(value)


# EOF
