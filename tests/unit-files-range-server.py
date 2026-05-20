import os
import socket
import subprocess
import sys
import time
import re
import urllib.request
from pathlib import Path


PORT_RE = re.compile(r"Port=(\d+)")
ALT_PORT_RE = re.compile(r"Found alternate available port:\s*(\d+)")


def waitForPort(output: str) -> int | None:
	for line in output.splitlines():
		if match := ALT_PORT_RE.search(line):
			return int(match.group(1))
		if match := PORT_RE.search(line):
			return int(match.group(1))
	return None


def main() -> int:
	root = Path(__file__).resolve().parent.parent
	target = root / "src" / "py" / "extra" / "server.py"
	expected = target.read_bytes()[3157:3214]
	size = target.stat().st_size

	blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
	blocker.bind(("127.0.0.1", 0))
	blocked_port = blocker.getsockname()[1]
	blocker.listen(1)

	env = dict(os.environ)
	env["PYTHONPATH"] = f"{root / 'src' / 'py'}{os.pathsep}{env['PYTHONPATH']}" if env.get("PYTHONPATH") else str(root / "src" / "py")
	process = subprocess.Popen(
		[
			sys.executable,
			"-u",
			"-m",
			"extra",
			"--host",
			"127.0.0.1",
			"--port",
			str(blocked_port),
		],
		cwd=str(root),
		env=env,
		stdout=subprocess.PIPE,
		stderr=subprocess.STDOUT,
		text=True,
	)

	selected_port: int | None = None
	output: list[str] = []
	deadline = time.monotonic() + 20.0
	try:
		assert process.stdout is not None
		while time.monotonic() < deadline:
			if process.poll() is not None:
				raise RuntimeError("server exited before becoming ready")
			line = process.stdout.readline()
			if line:
				output.append(line)
				if selected_port is None:
					selected_port = waitForPort("".join(output))
					if selected_port is not None:
						break
			else:
				time.sleep(0.05)

		if selected_port is None:
			raise RuntimeError(f"timed out waiting for server port; output={''.join(output)!r}")
		if selected_port == blocked_port:
			raise RuntimeError("server did not fall back to an alternate port")

		url = f"http://127.0.0.1:{selected_port}/src/py/extra/server.py?raw=1"
		request = urllib.request.Request(url, headers={"Range": "bytes=3157-3213"})
		with urllib.request.urlopen(request, timeout=10) as response:
			body = response.read()
			assert response.status == 206
			assert response.getheader("Content-Range") == f"bytes 3157-3213/{size}"
			assert response.getheader("Content-Length") == str(len(expected))
			assert body == expected

		print(f"✓ live range server test on {selected_port} (blocked {blocked_port})")
		return 0
	except Exception as e:
		print(f"✗ live range server test failed: {e}")
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
