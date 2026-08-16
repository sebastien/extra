#!/usr/bin/env python3

import ssl
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

from extra import HTTPRequest, HTTPResponse, Service, on, run


class HTTPSService(Service):
	@on(GET="/")
	def index(self, request: HTTPRequest) -> HTTPResponse:
		return request.respond(b"https works", "text/plain")


def main() -> None:
	with tempfile.TemporaryDirectory() as directory:
		with socket.socket() as probe:
			probe.bind(("127.0.0.1", 0))
			port = probe.getsockname()[1]
		cert = Path(directory) / "cert.pem"
		key = Path(directory) / "key.pem"
		subprocess.run(
			[
				"openssl",
				"req",
				"-x509",
				"-newkey",
				"rsa:2048",
				"-keyout",
				str(key),
				"-out",
				str(cert),
				"-days",
				"1",
				"-nodes",
				"-subj",
				"/CN=localhost",
			],
			check=True,
			stdout=subprocess.DEVNULL,
			stderr=subprocess.DEVNULL,
		)
		context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
		context.load_cert_chain(cert, key)
		stop = threading.Event()
		thread = threading.Thread(
			target=lambda: run(
				HTTPSService(),
				host="127.0.0.1",
				port=port,
				condition=lambda: not stop.is_set(),
				sslContext=context,
			),
			daemon=True,
		)
		thread.start()
		try:
			client = ssl._create_unverified_context()
			deadline = time.monotonic() + 5
			while time.monotonic() < deadline:
				try:
					with urllib.request.urlopen(
						f"https://127.0.0.1:{port}/", context=client, timeout=1
					) as response:
						assert response.read() == b"https works"
						print("OK! HTTPS server response")
						return
				except Exception:
					time.sleep(0.05)
			raise RuntimeError("HTTPS server did not become ready")
		finally:
			stop.set()
			thread.join(timeout=2)


if __name__ == "__main__":
	main()

# EOF
