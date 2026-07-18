from __future__ import annotations

from typing import Any, Callable

from ..http.model import HTTPRequest, HTTPResponse


def json(
	*,
	status: int = 500,
	statusByType: dict[type[BaseException], int] | None = None,
	payload: Callable[[BaseException, int], Any] | None = None,
) -> Callable[[HTTPRequest, BaseException], HTTPResponse]:
	def transform(request: HTTPRequest, error: BaseException) -> HTTPResponse:
		code = status
		if statusByType:
			for errorType, errorStatus in statusByType.items():
				if isinstance(error, errorType):
					code = errorStatus
					break
		body = payload(error, code) if payload else {"error": str(error)}
		return request.fail(body, status=code)

	return transform


# EOF
