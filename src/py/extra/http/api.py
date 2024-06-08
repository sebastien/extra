from typing import Any, Generic, TypeVar, Iterator
from abc import ABC, abstractmethod
from pathlib import Path

from .status import HTTP_STATUS
from ..utils.json import json

T = TypeVar("T")

# -----------------------------------------------------------------------------
#
# API
#
# -----------------------------------------------------------------------------

# --
# == HTTP Request Response API
#
# Defines the high level API functions (orthogonal to the underlying model)
# to manipulate requests/responses.


class ResponseFactory(ABC, Generic[T]):

    @abstractmethod
    def respond(
        self,
        content: Any = None,
        contentType: str | None = None,
        contentLength: int | None = None,
        status: int = 200,
        message: str | None = None,
    ) -> T: ...

    def error(
        self, status: int, content: str | None = None, contentType: str = "text/plain"
    ):
        message = HTTP_STATUS.get(status, "Server Error")
        return self.respond(
            content=message if content is None else content,
            contentType=contentType,
            status=status,
            message=message,
        )

    def notAuthorized(
        self,
        content: str = "Unauthorized",
        contentType="text/plain",
        *,
        status: int = 403
    ):
        return self.error(status, content=content, contentType=contentType)

    def notFound(
        self, content: str = "Not Found", contentType="text/plain", *, status: int = 404
    ):
        return self.error(status, content=content, contentType=contentType)

    def notModified(self):
        pass

    def fail(self):
        pass

    def redirect(self):
        pass

    def respondText(
        self, content: str | bytes | Iterator[str | bytes], contentType="text/plain"
    ):
        return self.respond(content=content, contentType=contentType)

    def respondHTML(self, html: str | bytes | Iterator[str | bytes]):
        return self.respond(content=html, contentType="text/html")

    def respondFile(self, path: Path | str, status: int = 200):
        return self.respond(
            content=path if isinstance(path, Path) else Path(path), status=status
        )

    def returns(self, value: Any):
        payload: bytes = json(value)
        return self.respond(
            payload, contentType="application/json", contentLength=len(payload)
        )


# EOF
