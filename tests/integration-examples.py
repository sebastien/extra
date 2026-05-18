from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"
DIRECTIVE_PATTERN = re.compile(
	r"^\s*#\s*(EXPECT|WAIT|TIMEOUT|GET|POST|PAYLOAD):\s*(.*?)\s*$"
)
DEFAULT_TIMEOUT = 6.0
TIMEOUTS: dict[str, float] = {
	"awslambda.py": 10.0,
	"client.py": 25.0,
	"client-gzip.py": 25.0,
}
DAEMON_EXAMPLES: set[str] = {
	"api.py",
	"capture.py",
	"cors.py",
	"fileserver.py",
	"helloworld.py",
	"htmx.py",
	"middleware.py",
	"proxy.py",
	"ssi.py",
	"sse.py",
	"upload.py",
	"watch.py",
	"workers.py",
}


@dataclass(slots=True)
class RunResult:
	name: str
	mode: str
	timeout: float
	returncode: int | None
	timed_out: bool
	killed: bool
	output: str
	expected: list[str]
	missing: list[str]
	error: str | None


@dataclass(slots=True)
class Directive:
	kind: str
	value: str
	line: int


@dataclass(slots=True)
class PortReservation:
	host: str
	port: int
	socket: socket.socket

	def release(self) -> None:
		self.socket.close()


def parse_directives(path: Path) -> list[Directive]:
	directives: list[Directive] = []
	for index, line in enumerate(
		path.read_text(encoding="utf-8").splitlines(), start=1
	):
		match = DIRECTIVE_PATTERN.match(line)
		if match:
			directives.append(
				Directive(
					kind=match.group(1),
					value=match.group(2).strip(),
					line=index,
				)
			)
	return directives


def reserve_free_port(host: str = "127.0.0.1") -> PortReservation:
	sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
	sock.bind((host, 0))
	port = int(sock.getsockname()[1])
	return PortReservation(host=host, port=port, socket=sock)


def is_port_free(host: str, port: int) -> bool:
	probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
	try:
		probe.bind((host, port))
		return True
	except OSError:
		return False
	finally:
		probe.close()


def parse_duration(value: str) -> float:
	raw = value.strip().lower()
	if raw.endswith("ms"):
		return float(raw[:-2]) / 1000.0
	if raw.endswith("s"):
		return float(raw[:-1])
	if not raw:
		raise ValueError("empty duration")
	return float(raw)


def resolve_url(raw: str, host: str, port: int) -> str:
	formatted = raw.format(HOST=host, PORT=port)
	if formatted.startswith("http://") or formatted.startswith("https://"):
		return formatted
	if formatted.startswith("/"):
		return f"http://{host}:{port}{formatted}"
	return f"http://{host}:{port}/{formatted}"


def run_http_request(
	method: str, url: str, payload: str | None, timeout: float
) -> tuple[bool, str]:
	body: bytes | None = None
	headers: dict[str, str] = {}
	if payload is not None:
		try:
			parsed = json.loads(payload)
			body = json.dumps(parsed).encode("utf-8")
			headers["Content-Type"] = "application/json"
		except json.JSONDecodeError:
			body = payload.encode("utf-8")
			headers["Content-Type"] = "text/plain; charset=utf-8"
	request = urllib.request.Request(url=url, data=body, headers=headers, method=method)
	try:
		with urllib.request.urlopen(request, timeout=timeout) as response:
			content = response.read().decode("utf-8", errors="replace")
			return True, f"HTTP {method} {url} -> {response.status}\\n{content}"
	except urllib.error.HTTPError as error:
		content = error.read().decode("utf-8", errors="replace")
		return False, f"HTTP {method} {url} -> {error.code}\\n{content}"
	except Exception as error:
		return False, f"HTTP {method} {url} -> ERROR\\n{error}"


def missing_in_order(output: str, expected: list[str]) -> list[str]:
	missing: list[str] = []
	offset = 0
	for item in expected:
		index = output.find(item, offset)
		if index < 0:
			missing.append(item)
		else:
			offset = index + len(item)
	return missing


def run_example(path: Path) -> RunResult:
	directives = parse_directives(path)
	expected = [d.value for d in directives if d.kind == "EXPECT"]
	mode = "daemon" if path.name in DAEMON_EXAMPLES else "finite"
	if not directives:
		return RunResult(
			name=path.name,
			mode=mode,
			timeout=0,
			returncode=None,
			timed_out=False,
			killed=False,
			output="",
			expected=[],
			missing=[
				"No directives found (# EXPECT:, # WAIT:, # TIMEOUT:, # GET:, # POST:)"
			],
			error=None,
		)

	timeout = TIMEOUTS.get(path.name, DEFAULT_TIMEOUT)
	for directive in directives:
		if directive.kind == "TIMEOUT":
			timeout = parse_duration(directive.value)
	env = os.environ.copy()
	env["PYTHONUNBUFFERED"] = "1"
	reservation = reserve_free_port("127.0.0.1")
	if not is_port_free(reservation.host, reservation.port):
		reservation.release()
		reservation = reserve_free_port("127.0.0.1")
	env["HOST"] = reservation.host
	env["PORT"] = str(reservation.port)
	pythonpath = str(ROOT / "src" / "py")
	if env.get("PYTHONPATH"):
		env["PYTHONPATH"] = f"{pythonpath}{os.pathsep}{env['PYTHONPATH']}"
	else:
		env["PYTHONPATH"] = pythonpath
	command = [sys.executable, "-u", str(path)]
	process = subprocess.Popen(
		command,
		cwd=str(ROOT),
		stdout=subprocess.PIPE,
		stderr=subprocess.STDOUT,
		text=True,
		env=env,
	)

	reservation.release()
	timed_out = False
	killed = False
	error: str | None = None
	chunks: list[str] = []
	chunk_lock = threading.Lock()

	def reader() -> None:
		assert process.stdout is not None
		for line in process.stdout:
			with chunk_lock:
				chunks.append(line)

	thread = threading.Thread(target=reader, daemon=True)
	thread.start()
	deadline = time.monotonic() + timeout
	offset = 0
	pending_payload: str | None = None

	def snapshot_output() -> str:
		with chunk_lock:
			return "".join(chunks)

	def wait_for_expect(text: str) -> bool:
		nonlocal offset
		while time.monotonic() < deadline:
			output = snapshot_output()
			index = output.find(text, offset)
			if index >= 0:
				offset = index + len(text)
				return True
			if process.poll() is not None:
				break
			time.sleep(0.05)
		output = snapshot_output()
		index = output.find(text, offset)
		if index >= 0:
			offset = index + len(text)
			return True
		return False

	try:
		for idx, directive in enumerate(directives, start=1):
			if time.monotonic() >= deadline:
				timed_out = True
				error = f"Directive #{idx} timed out ({directive.kind} on line {directive.line})"
				break

			if directive.kind == "EXPECT":
				if not wait_for_expect(directive.value):
					error = (
						f"Directive #{idx} failed: EXPECT on line {directive.line}: "
						f"{directive.value}"
					)
					break
			elif directive.kind == "WAIT":
				remaining = max(0.0, deadline - time.monotonic())
				delay = min(parse_duration(directive.value), remaining)
				time.sleep(delay)
			elif directive.kind == "TIMEOUT":
				continue
			elif directive.kind == "PAYLOAD":
				pending_payload = directive.value
			elif directive.kind in {"GET", "POST"}:
				url = resolve_url(directive.value, reservation.host, reservation.port)
				request_timeout = max(0.1, deadline - time.monotonic())
				payload = pending_payload if directive.kind == "POST" else None
				pending_payload = None
				success, request_log = run_http_request(
					directive.kind,
					url,
					payload,
					min(request_timeout, 5.0),
				)
				with chunk_lock:
					chunks.append(request_log + "\n")
				if not success:
					error = (
						f"Directive #{idx} failed: {directive.kind} on line {directive.line}: "
						f"{url}"
					)
					break

		if error is None and mode == "finite":
			remaining = max(0.1, deadline - time.monotonic())
			try:
				process.wait(timeout=remaining)
			except subprocess.TimeoutExpired:
				timed_out = True
		elif error is None and mode == "daemon":
			killed = True
			process.terminate()
			try:
				process.wait(timeout=2.0)
			except subprocess.TimeoutExpired:
				process.kill()
				process.wait(timeout=2.0)
	finally:
		if process.poll() is None:
			if mode == "daemon":
				killed = True
			process.terminate()
			try:
				process.wait(timeout=2.0)
			except subprocess.TimeoutExpired:
				process.kill()
				process.wait(timeout=2.0)
		thread.join(timeout=1.0)

	output = snapshot_output()

	missing = missing_in_order(output, expected)
	return RunResult(
		name=path.name,
		mode=mode,
		timeout=timeout,
		returncode=process.returncode,
		timed_out=timed_out,
		killed=killed,
		output=output,
		expected=expected,
		missing=missing,
		error=error,
	)


def format_output_excerpt(output: str, lines: int = 25) -> str:
	content = output.strip()
	if not content:
		return "<empty output>"
	all_lines = content.splitlines()
	if len(all_lines) <= lines:
		return "\n".join(all_lines)
	return "\n".join(all_lines[-lines:])


def main() -> int:
	example_files = sorted(p for p in EXAMPLES.glob("*.py") if p.is_file())
	if not example_files:
		print("No example files found")
		return 1

	failures: list[RunResult] = []
	for path in example_files:
		result = run_example(path)

		has_runtime_failure = False
		if result.timed_out:
			has_runtime_failure = True
		elif result.mode == "finite":
			has_runtime_failure = (
				result.returncode is not None and result.returncode != 0
			)
		elif not result.killed:
			has_runtime_failure = (
				result.returncode is not None and result.returncode != 0
			)
		is_failure = bool(result.missing) or has_runtime_failure
		if result.error is not None:
			is_failure = True
		status = "FAIL" if is_failure else "PASS"
		if result.timed_out:
			detail = "timeout"
		elif result.killed:
			detail = "verified+stopped"
		else:
			detail = f"exit={result.returncode}"
		print(f"[{status}] {result.name} ({detail})")

		if is_failure:
			failures.append(result)

	if failures:
		print("\nExample integration failures:")
		for result in failures:
			print(f"\n- {result.name}")
			if result.missing:
				for item in result.missing:
					print(f"    Missing EXPECT: {item}")
			if result.error is not None:
				print(f"    {result.error}")
			if result.timed_out:
				print(f"    Process timed out after {result.timeout:.1f}s")
			elif (result.mode == "finite" or not result.killed) and (
				result.returncode is not None and result.returncode != 0
			):
				print(f"    Process failed with exit code {result.returncode}")
			print("    Output excerpt:")
			excerpt = format_output_excerpt(result.output)
			for line in excerpt.splitlines():
				print(f"      {line}")
		return 1

	print(f"\nAll {len(example_files)} examples matched their EXPECT lines.")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())

# EOF
