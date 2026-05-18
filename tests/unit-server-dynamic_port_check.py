#!/usr/bin/env python3
import argparse
import os
import random
import re
import socket
import subprocess
import sys
import time
import urllib.request
from hashlib import sha256


PORT_RE = re.compile(r"Port=(?P<port>\d+)")
ALT_PORT_RE = re.compile(r"Found alternate available port:\s*(?P<port>\d+)")


def pick_port(line: str) -> int | None:
	if m := ALT_PORT_RE.search(line):
		return int(m.group("port"))
	if m := PORT_RE.search(line):
		return int(m.group("port"))
	return None


def check_complete(host: str, port: int) -> None:
	random.seed(512)
	count = 1_000 + random.randint(0, 1_000)
	body = b"-".join(b"%d" % (_) for _ in range(count))
	expected = f"Read:{sha256(body).hexdigest()}"
	request = urllib.request.Request(f"http://{host}:{port}/upload", data=body)
	with urllib.request.urlopen(request, timeout=10) as response:
		payload = response.read().decode("utf8")
		if not payload.startswith(expected):
			raise RuntimeError(f"Unexpected response: {payload}")


def check_partial(host: str, port: int) -> None:
	body = b"x" * 2048
	request = urllib.request.Request(f"http://{host}:{port}/upload", data=body)
	with urllib.request.urlopen(request, timeout=10) as response:
		payload = response.read().decode("utf8")
		expected = f"Read: {len(body)}"
		if payload != expected:
			raise RuntimeError(f"Unexpected response: {payload}")


def main() -> int:
	parser = argparse.ArgumentParser(
		description="Check server with dynamic port fallback"
	)
	parser.add_argument("--server", required=True)
	parser.add_argument("--mode", choices=("complete", "partial"), required=True)
	parser.add_argument("--timeout", type=float, default=20.0)
	parser.add_argument("--host", default="127.0.0.1")
	args = parser.parse_args()

	blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
	blocker.bind((args.host, 0))
	blocked_port = blocker.getsockname()[1]
	blocker.listen(1)

	env = dict(os.environ)
	env["PORT"] = str(blocked_port)
	env["HOST"] = args.host

	process = subprocess.Popen(
		[sys.executable, args.server],
		stdout=subprocess.PIPE,
		stderr=subprocess.STDOUT,
		text=True,
		env=env,
	)

	selected_port: int | None = None
	deadline = time.monotonic() + args.timeout
	try:
		assert process.stdout is not None
		while time.monotonic() < deadline:
			if process.poll() is not None:
				raise RuntimeError("Server process exited before becoming ready")
			line = process.stdout.readline()
			if line:
				if port := pick_port(line):
					selected_port = port
					break
			else:
				time.sleep(0.05)

		if selected_port is None:
			raise RuntimeError("Timed out waiting for selected server port")
		if selected_port == blocked_port:
			raise RuntimeError("Server did not fallback to an alternate port")

		for _ in range(30):
			try:
				with socket.create_connection((args.host, selected_port), timeout=0.2):
					break
			except OSError:
				time.sleep(0.1)
		else:
			raise RuntimeError("Server did not accept connections on selected port")

		if args.mode == "complete":
			check_complete(args.host, selected_port)
		else:
			check_partial(args.host, selected_port)

		print(
			f"✓ {args.mode} dynamic-port server test on {selected_port} (blocked {blocked_port})"
		)
		return 0
	except Exception as e:
		print(f"✗ {args.mode} dynamic-port server test failed: {e}")
		return 1
	finally:
		process.terminate()
		try:
			process.wait(timeout=2)
		except subprocess.TimeoutExpired:
			process.kill()
			process.wait(timeout=2)
		blocker.close()


if __name__ == "__main__":
	raise SystemExit(main())


# EOF
