#!/usr/bin/env python3
import random
import re
import socket
import subprocess
import time
from time import perf_counter_ns


SEPARATOR = "-" * 72
AB_RPS_RE = re.compile(r"Requests per second:\s+([\d.]+)")
H2_RPS_RE = re.compile(r"finished in .*?,\s*([\d\.]+)\s*req/s")

MODE_ORDER: tuple[str, ...] = (
	"h10_close_legacy",
	"h10_keepalive_legacy",
	"h1_close",
	"h1_keepalive_serial",
	"h1_keepalive_pipeline",
)

MODE_LABELS: dict[str, str] = {
	"h10_close_legacy": "HTTP/1.0 close via ab",
	"h10_keepalive_legacy": "HTTP/1.0 keep-alive via ab -k",
	"h1_close": "HTTP/1.1 close via h2load --h1 -H 'Connection: close'",
	"h1_keepalive_serial": "HTTP/1.1 keep-alive serial via h2load --h1 -m1",
	"h1_keepalive_pipeline": "HTTP/1.1 keep-alive pipelined via h2load --h1 -m10",
}

MODE_TOOLS: dict[str, str] = {
	"h10_close_legacy": "ab",
	"h10_keepalive_legacy": "ab",
	"h1_close": "h2load",
	"h1_keepalive_serial": "h2load",
	"h1_keepalive_pipeline": "h2load",
}


def print_header(title: str) -> None:
	print(f"\n{SEPARATOR}")
	print(f"  {title}")
	print(SEPARATOR)


def print_result(name: str, iterations: int, elapsed_ns: int, extra: str = "") -> float:
	ns_op = elapsed_ns / iterations
	ops_s = iterations * 1_000_000_000 / elapsed_ns if elapsed_ns else 0.0
	line = (
		f"{name:28} ops={iterations:9d} time={elapsed_ns / 1_000_000:10.3f}ms "
		f"ns/op={ns_op:10.1f} ops/s={ops_s:12.1f}"
	)
	if extra:
		line += f"  {extra}"
	print(line)
	return ns_op


def print_comparison(
	label: str, baseline_ns: float, other_ns: float, other_name: str
) -> None:
	if baseline_ns <= 0 or other_ns <= 0:
		return
	ratio = other_ns / baseline_ns
	if ratio >= 1:
		print(
			f"  {label:26} baseline: {baseline_ns:10.1f}  {other_name}: {other_ns:10.1f} ns/op "
			f" => baseline is {ratio:.1f}x faster"
		)
	else:
		print(
			f"  {label:26} baseline: {baseline_ns:10.1f}  {other_name}: {other_ns:10.1f} ns/op "
			f" => {other_name} is {1 / ratio:.1f}x faster"
		)


def build_routing_scenarios(
	static_routes: int, param_routes: int, sample_size: int
) -> dict[str, list[str]]:
	scenarios: dict[str, list[str]] = {
		"static-hit": [f"/static/{i % static_routes}" for i in range(sample_size)],
		"param-hit": [
			f"/users/{i % param_routes}/{(i * 7) % 10_000}" for i in range(sample_size)
		],
		"miss": [f"/missing/{i}/path" for i in range(sample_size)],
	}
	mixed = (
		list(scenarios["static-hit"])
		+ list(scenarios["param-hit"])
		+ list(scenarios["miss"])
	)
	random.Random(42).shuffle(mixed)
	scenarios["mixed"] = mixed
	return scenarios


def build_reqres_scenarios(sample_size: int) -> dict[str, list[str]]:
	scenarios: dict[str, list[str]] = {
		"plain": ["/plain"] * sample_size,
		"json": ["/json"] * sample_size,
		"param": [f"/users/{(i * 17) % 10_000}" for i in range(sample_size)],
		"async": [f"/async/{(i * 11) % 10_000}" for i in range(sample_size)],
	}
	mixed_paths: list[str] = []
	for paths in scenarios.values():
		mixed_paths.extend(paths)
	random.Random(7).shuffle(mixed_paths)
	scenarios["mixed"] = mixed_paths
	return scenarios


def benchmark_loop(callable_fn, items: list, iterations: int, warmup: int) -> int:
	n = len(items)
	for i in range(warmup):
		callable_fn(items[i % n])
	start = perf_counter_ns()
	for i in range(iterations):
		callable_fn(items[i % n])
	return perf_counter_ns() - start


def wait_for_port(host: str, port: int, timeout: float = 10.0) -> bool:
	deadline = time.monotonic() + timeout
	while time.monotonic() < deadline:
		try:
			with socket.create_connection((host, port), timeout=0.5):
				return True
		except OSError:
			time.sleep(0.1)
	return False


def stop_process(proc: subprocess.Popen[str]) -> None:
	if proc.poll() is not None:
		return
	proc.terminate()
	try:
		proc.wait(timeout=3)
	except subprocess.TimeoutExpired:
		proc.kill()
		proc.wait(timeout=3)


def run_ab(
	host: str, port: int, path: str, requests: int, concurrency: int
) -> float | None:
	cmd = ["ab", f"-n{requests}", f"-c{concurrency}", f"http://{host}:{port}{path}"]
	result = subprocess.run(cmd, capture_output=True, text=True)
	if result.returncode != 0:
		return None
	match = AB_RPS_RE.search(result.stdout)
	return float(match.group(1)) if match else None


def parse_h2load_rps(output: str) -> float | None:
	match = H2_RPS_RE.search(output)
	if not match:
		return None
	return float(match.group(1))


def parse_modes(raw: str) -> tuple[str, ...]:
	if raw == "all":
		return MODE_ORDER
	modes: list[str] = []
	for item in raw.split(","):
		mode = item.strip()
		if not mode:
			continue
		if mode not in MODE_LABELS:
			raise ValueError(f"unknown mode '{mode}'")
		if mode not in modes:
			modes.append(mode)
	if not modes:
		raise ValueError("no benchmark modes selected")
	return tuple(modes)


def required_tools_for_modes(modes: tuple[str, ...]) -> tuple[str, ...]:
	return tuple(sorted({MODE_TOOLS[mode] for mode in modes}))


def build_mode_command(
	mode: str, host: str, port: int, path: str, requests: int, concurrency: int
) -> list[str]:
	url = f"http://{host}:{port}{path}"
	if mode == "h10_close_legacy":
		return ["ab", f"-n{requests}", f"-c{concurrency}", url]
	if mode == "h10_keepalive_legacy":
		return ["ab", "-k", f"-n{requests}", f"-c{concurrency}", url]
	if mode == "h1_close":
		return [
			"h2load",
			f"-n{requests}",
			f"-c{concurrency}",
			"-m1",
			"--h1",
			"-H",
			"Connection: close",
			url,
		]
	if mode == "h1_keepalive_serial":
		return ["h2load", f"-n{requests}", f"-c{concurrency}", "-m1", "--h1", url]
	if mode == "h1_keepalive_pipeline":
		return ["h2load", f"-n{requests}", f"-c{concurrency}", "-m10", "--h1", url]
	raise ValueError(f"unknown mode '{mode}'")


def parse_mode_rps(mode: str, output: str) -> float | None:
	if mode.startswith("h10_"):
		match = AB_RPS_RE.search(output)
		return float(match.group(1)) if match else None
	return parse_h2load_rps(output)


def run_mode(
	mode: str, host: str, port: int, path: str, requests: int, concurrency: int
) -> float | None:
	cmd = build_mode_command(mode, host, port, path, requests, concurrency)
	result = subprocess.run(cmd, capture_output=True, text=True)
	output = f"{result.stdout}\n{result.stderr}"
	rps = parse_mode_rps(mode, output)
	if rps is not None:
		return rps
	if result.returncode != 0:
		return None
	return None


def bench_server(
	name: str,
	command: list[str],
	env: dict[str, str],
	host: str,
	port: int,
	requests: int,
	concurrency: int,
	modes: tuple[str, ...],
) -> dict[str, float | None] | None:
	proc = subprocess.Popen(
		command, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True
	)
	try:
		if not wait_for_port(host, port):
			stderr = proc.stderr.read().strip() if proc.stderr else ""
			msg = stderr.splitlines()[-1] if stderr else "server did not start"
			print(f"  {name}: SKIP ({msg})")
			return None
		warmup_requests = min(requests // 10, 1000)
		if warmup_requests > 0 and modes:
			run_mode(modes[0], host, port, "/", warmup_requests, min(concurrency, 50))
		results: dict[str, float | None] = {}
		for mode in modes:
			results[mode] = run_mode(mode, host, port, "/", requests, concurrency)
		return results
	finally:
		stop_process(proc)


# EOF
