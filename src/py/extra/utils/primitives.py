from typing import TypeVar, Any
from time import struct_time
from decimal import Decimal
from datetime import date, datetime
from dataclasses import is_dataclass
from pathlib import Path
from enum import Enum

T = TypeVar("T")


TLiteral = bool | int | float | str | bytes
TComposite = (
    list[TLiteral] | dict[TLiteral, TLiteral] | set[TLiteral] | tuple[TLiteral, ...]
)
TComposite2 = (
    list[TLiteral | TComposite]
    | dict[TLiteral, TLiteral | TComposite]
    | set[TLiteral | TComposite]
    | tuple[TLiteral | TComposite, ...]
)
TComposite3 = (
    list[TLiteral | TComposite | TComposite2]
    | dict[TLiteral, TLiteral | TComposite | TComposite2]
    | set[TLiteral | TComposite | TComposite2]
    | tuple[TLiteral | TComposite | TComposite2, ...]
)
TPrimitive = bool | int | float | str | bytes | TComposite | TComposite | TComposite3


def asPrimitive(value: Any, *, currentDepth: int = 0) -> Any:
    """Converts the given value to a primitive value, that can be converted
    to JSON"""
    if value is None or type(value) in (bool, float, int, str):
        return value
    elif isinstance(value, tuple) and hasattr(value, "_fields"):
        t = type(value)
        f = getattr(t, "asPrimitive") if t and hasattr(t, "asPrimitive") else None
        return (
            f(value)
            if f
            else (
                {
                    asPrimitive(k): asPrimitive(
                        getattr(value, k), currentDepth=currentDepth + 1
                    )
                    for k in value._fields
                }
                if hasattr(value, "_fields")
                else f
            )
        )
    elif isinstance(value, list) or isinstance(value, tuple) or isinstance(value, set):
        return [asPrimitive(v, currentDepth=currentDepth + 1) for v in value]
    elif is_dataclass(value):
        return {
            asPrimitive(k): asPrimitive(
                getattr(value, k), currentDepth=currentDepth + 1
            )
            for k in value.__annotations__
        }
    elif isinstance(value, Enum):
        return asPrimitive(value.value)
    elif isinstance(value, dict):
        return {
            asPrimitive(k): asPrimitive(v, currentDepth=currentDepth + 1)
            for k, v in value.items()
        }
    elif isinstance(value, Decimal):
        return str(value)
    elif isinstance(value, Path):
        return str(value)
    elif isinstance(value, datetime) or isinstance(value, date):
        return tuple(value.timetuple())
    elif isinstance(value, struct_time):
        return tuple(value)
    else:
        return value


# EOF
