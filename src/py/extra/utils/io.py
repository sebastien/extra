DEFAULT_ENCODING: str = "utf8"


def asBytes(value: str | bytes) -> bytes:
    if isinstance(value, bytes):
        return value
    elif isinstance(value, str):
        return bytes(value, DEFAULT_ENCODING)
    elif value is None:
        return b""
    else:
        raise ValueError(f"Expected bytes or str, got: {value}")


# EOF
