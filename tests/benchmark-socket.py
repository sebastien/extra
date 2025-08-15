#!/usr/bin/python
import os
import socket

RESPONSE = b"""HTTP/1.1 200 OK\r
Content-Type: text/plain\r
Content-Length: 12\r
\r
Hello, World!"""

BACKLOG: int = int(os.getenv("HTTP_BACKLOG", 1_000))
BUFFER: int = int(os.getenv("HTTP_BUFFER", 64_000))
PORT: int = int(os.getenv("HTTP_PORT", 8000))


def server(host: str = "0.0.0.0", port: int = PORT):
	print(f"Vanilla HTTP server on {host}:{port}")

	server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
	server.bind((host, port))
	server.listen(BACKLOG)

	bufsize: int = BUFFER

	while True:
		client, address = server.accept()
		ends: bool = False
		while not ends:
			data: bytes = client.recv(bufsize)
			ends = len(data) < bufsize
		client.sendall(RESPONSE)
		client.close()


if __name__ == "__main__":
	server()
# EOF
