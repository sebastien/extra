#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "py"
if str(SRC) not in sys.path:
	sys.path.insert(0, str(SRC))

from extra import server
from extra.http.model import HTTPHeaders, HTTPRequest


def main() -> None:
	request = HTTPRequest(
		"GET",
		"/missing",
		{"debug": "true"},
		HTTPHeaders({}, contentType="text/plain", contentLength=0),
	)
	warnings: list[tuple[str, dict[str, Any]]] = []
	errors: list[tuple[str, int, dict[str, Any]]] = []

	def captureWarning(message: str, **context: Any) -> None:
		warnings.append((message, context))

	def captureError(message: str, code: int, **context: Any) -> None:
		errors.append((message, code, context))

	oldWarning = server.warning
	oldError = server.error
	server.warning = captureWarning  # type: ignore[assignment]
	server.error = captureError  # type: ignore[assignment]
	try:
		server.ServerState().onResponseError(request, 404, "Not Found")
		server.ServerState().onResponseError(request, 503, "Service Unavailable")
	finally:
		server.warning = oldWarning
		server.error = oldError

	assert warnings == [
		(
			"HTTP 404 Not Found",
			{
				"Method": "GET",
				"Path": "/missing",
				"Status": 404,
				"Query": "{'debug': 'true'}",
			},
		)
	]
	assert errors == [
		(
			"HTTP 503 Service Unavailable",
			503,
			{
				"Method": "GET",
				"Path": "/missing",
				"Status": 503,
				"Query": "{'debug': 'true'}",
			},
		)
	]
	print("OK! HTTP error responses are logged with request details")


if __name__ == "__main__":
	main()

# EOF
