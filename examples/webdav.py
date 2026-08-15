"""Expose a virtual, read-only filesystem over WebDAV."""
# EXPECT: WebDAV demo available
# WAIT: 0.3s
# GET: /dav/README.txt
# EXPECT: virtual WebDAV filesystem

import os
import socket

from extra import run
from extra.features.webdav import MemoryWebDAVBackend, WebDAVService
from extra.utils.logging import info


backend = MemoryWebDAVBackend(
	{
		"/README.txt": "This is a virtual WebDAV filesystem.\n",
		"/notes/welcome.txt": "Browse me with a WebDAV client.\n",
	},
	writable=True,
)


if __name__ == "__main__":
	host = os.getenv("HOST", "0.0.0.0")
	port = int(os.getenv("PORT", "8000"))
	for candidate in range(port, port + 5):
		with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
			try:
				probe.bind((host, candidate))
			except OSError:
				continue
			port = candidate
			break
	connectHost = os.getenv("HOSTNAME", socket.gethostname())
	endpoint = f"http://{connectHost}:{port}/dav/"
	info("WebDAV demo available", URL=endpoint)
	info("List resources with curl", Command=f"curl -X PROPFIND -H 'Depth: 1' {endpoint}")
	info("Download a file with curl", Command=f"curl {endpoint}README.txt")
	info("Upload a file with curl", Command=f"curl -T local.txt {endpoint}uploads/local.txt")
	info("Mount with gio", Command=f"gio mount dav://{connectHost}:{port}/dav/")
	info("Open in GNOME Files", URL=f"dav://{connectHost}:{port}/dav/")
	run(WebDAVService(backend, prefix="dav"), host=host, port=port)

# EOF
