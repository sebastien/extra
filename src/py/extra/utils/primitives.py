from typing import TypeVar

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
# EOF
