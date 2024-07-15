import mimetypes
from pathlib import Path

MIME_TYPES: dict[str, str] = dict(
    bz2="application/x-bzip",
    gz="application/x-gzip",
)


def contentType(path: Path | str) -> str:
    """Guesses the content type from the given path"""
    name = str(path)
    return (
        res
        if (res := MIME_TYPES.get(name.rsplit(".", 1)[-1].lower()))
        else mimetypes.guess_type(path)[0] or "text/plain"
    )


# EOF
