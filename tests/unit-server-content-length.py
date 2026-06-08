#!/usr/bin/env python3

from __future__ import annotations

import threading
import time
import urllib.error
import urllib.request
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "py"

if str(SRC) not in sys.path:
	sys.path.insert(0, str(SRC))

from extra import HTTPRequest, HTTPResponse, Service, on, run
from extra.http.model import HTTPBodyBlob, HTTPHeaders


BODY = b"x" * 4096


class ContentLengthService(Service):
	@on(GET="/")
	def read(self, request: HTTPRequest) -> HTTPResponse:
		return HTTPResponse(
			protocol=request.protocol,
			status=200,
			message="OK",
			headers=HTTPHeaders({"Content-Type": "text/plain"}),
			body=HTTPBodyBlob(BODY, len(BODY)),
		)


def main() -> None:
	stop = threading.Event()
	port = 8123

	thread = threading.Thread(
		target=lambda: run(
			ContentLengthService(),
			host="127.0.0.1",
			port=port,
			condition=lambda: not stop.is_set(),
		),
		daemon=True,
	)
	thread.start()

	try:
		deadline = time.monotonic() + 5.0
		while time.monotonic() < deadline:
			try:
				with urllib.request.urlopen(
					f"http://127.0.0.1:{port}/", timeout=1.0
				) as response:
					payload = response.read()
					assert payload == BODY, f"Unexpected body length: {len(payload)}"
					assert response.headers.get("Content-Length") == str(len(BODY))
					print("OK! response content-length was synthesized")
					return
			except urllib.error.URLError:
				time.sleep(0.05)
		raise RuntimeError("Server did not become ready")
	finally:
		stop.set()
		thread.join(timeout=2.0)


if __name__ == "__main__":
	main()

# EOF
