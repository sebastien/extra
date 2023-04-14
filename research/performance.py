# Idea: Creating the response object creates something that is in a straight format that
# can be serialized as a stream:

# Body can be: bytes, Iterator[bytes] or AsyncIterator[bytes]
@dataclass(slots=True)
class Response:
    chunks: list[bytes]
    startHeaders: int = 0
    endHeaders: int = 0
    bodies: []


# EOF
