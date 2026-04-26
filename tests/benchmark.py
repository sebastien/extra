#!/usr/bin/env python3
import argparse
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
SRC_PY = ROOT / "src" / "py"


RPS_AB_RE = re.compile(r"Requests per second:\s+([\d\.]+)")
RPS_H2_RE = re.compile(r"finished in .*?,\s*([\d\.]+)\s*req/s")


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


@dataclass(frozen=True)
class ServerBench:
	name: str
	command: tuple[str, ...]


SERVERS: tuple[ServerBench, ...] = (
	ServerBench("extra-aio", ("python", str(TESTS / "benchmark-extra-aio.py"))),
	ServerBench("socket", ("python", str(TESTS / "benchmark-socket.py"))),
	ServerBench("aiosocket", ("python", str(TESTS / "benchmark-aiosocket.py"))),
	ServerBench("aioserver", ("python", str(TESTS / "benchmark-aioserver.py"))),
	ServerBench("aiohttp", ("python", str(TESTS / "benchmark-aiohttp.py"))),
	ServerBench("raw-asgi", ("bash", str(TESTS / "benchmark-raw.sh"))),
	ServerBench("fastapi", ("bash", str(TESTS / "benchmark-fastapi.sh"))),
)


def mk_env() -> dict[str, str]:
	env = dict(os.environ)
	pythonpath = env.get("PYTHONPATH", "")
	src = str(SRC_PY)
	env["PYTHONPATH"] = f"{src}:{pythonpath}" if pythonpath else src
	return env


def run_core(label: str, routing_args: list[str], reqres_args: list[str], env: dict[str, str]) -> int:
	print(f"=== Running core benchmarks ({label})", flush=True)
	with tempfile.NamedTemporaryFile(mode="wt", delete=False) as routing_out, tempfile.NamedTemporaryFile(
		mode="wt", delete=False
	) as reqres_out:
		routing_path = routing_out.name
		reqres_path = reqres_out.name
	try:
		routing_cmd = [sys.executable, str(TESTS / "benchmark-routing.py"), *routing_args]
		reqres_cmd = [sys.executable, str(TESTS / "benchmark-reqres.py"), *reqres_args]
		routing_result = subprocess.run(routing_cmd, env=env, check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
		if routing_result.returncode != 0:
			print(routing_result.stdout.rstrip())
			print("ERR benchmark-routing failed")
			return routing_result.returncode
		Path(routing_path).write_text(routing_result.stdout, encoding="utf8")

		reqres_result = subprocess.run(reqres_cmd, env=env, check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
		if reqres_result.returncode != 0:
			print(reqres_result.stdout.rstrip())
			print("ERR benchmark-reqres failed")
			return reqres_result.returncode
		Path(reqres_path).write_text(reqres_result.stdout, encoding="utf8")

		table_cmd = [
			sys.executable,
			str(TESTS / "benchmark-table.py"),
			"--routing",
			routing_path,
			"--reqres",
			reqres_path,
			"--label",
			label,
		]
		table_result = subprocess.run(table_cmd, env=env, check=False)
		if table_result.returncode != 0:
			print("ERR benchmark-table failed")
			return table_result.returncode
		return 0
	finally:
		for path in (routing_path, reqres_path):
			if Path(path).exists():
				Path(path).unlink()


def wait_for_port(host: str, port: int, timeout: float = 10.0) -> bool:
	deadline = time.monotonic() + timeout
	while time.monotonic() < deadline:
		try:
			with socket.create_connection((host, port), timeout=0.5):
				return True
		except OSError:
			time.sleep(0.1)
	return False


def parse_ab_rps(output: str) -> str | None:
	match = RPS_AB_RE.search(output)
	if not match:
		return None
	return match.group(1)


def parse_h2load_rps(output: str) -> str | None:
	match = RPS_H2_RE.search(output)
	if not match:
		return None
	return match.group(1)


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


def build_mode_command(mode: str, host: str, port: int, requests: int, concurrency: int) -> list[str]:
	url = f"http://{host}:{port}/"
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


def parse_mode_rps(mode: str, output: str) -> str | None:
	if mode.startswith("h10_"):
		return parse_ab_rps(output)
	return parse_h2load_rps(output)


def run_mode(
	mode: str,
	env: dict[str, str],
	host: str,
	port: int,
	requests: int,
	concurrency: int,
) -> tuple[str, bool]:
	cmd = build_mode_command(mode, host, port, requests, concurrency)
	result = subprocess.run(cmd, env=env, check=False, capture_output=True, text=True)
	output = f"{result.stdout}\n{result.stderr}"
	rps = parse_mode_rps(mode, output)
	if not rps:
		if result.returncode != 0:
			return (f"ERR rc={result.returncode}", False)
		return ("ERR parse", False)
	if result.returncode != 0:
		return (f"{rps}* rc={result.returncode}", False)
	return (rps, True)


def stop_process(proc: subprocess.Popen[str]) -> None:
	if proc.poll() is not None:
		return
	proc.terminate()
	try:
		proc.wait(timeout=3)
	except subprocess.TimeoutExpired:
		proc.kill()
		proc.wait(timeout=3)


def run_server_bench(
	bench: ServerBench,
	env: dict[str, str],
	host: str,
	port: int,
	requests: int,
	concurrency: int,
	modes: tuple[str, ...],
) -> tuple[str, dict[str, str], str]:
	proc = subprocess.Popen(
		list(bench.command),
		env=env,
		stdout=subprocess.DEVNULL,
		stderr=subprocess.PIPE,
		text=True,
	)
	try:
		if not wait_for_port(host, port):
			stderr = ""
			if proc.stderr is not None:
				stderr = proc.stderr.read().strip()
			msg = stderr.splitlines()[-1] if stderr else "server did not start"
			cells = {mode: "-" for mode in modes}
			return ("SKIP", cells, msg)

		cells: dict[str, str] = {}
		failures = 0
		for mode in modes:
			cell, ok = run_mode(mode, env, host, port, requests, concurrency)
			cells[mode] = cell
			if not ok:
				failures += 1
		status = "OK" if failures == 0 else ("WARN" if failures < len(modes) else "ERR")
		return (status, cells, "")
	finally:
		stop_process(proc)


def run_server_suite(
	env: dict[str, str],
	requests: int,
	concurrency: int,
	host: str,
	port: int,
	modes: tuple[str, ...],
) -> int:
	required = sorted({MODE_TOOLS[mode] for mode in modes})
	missing = [cmd for cmd in required if shutil.which(cmd) is None]
	if missing:
		print(f"=== Server benchmark suite skipped (missing: {', '.join(missing)})")
		return 0

	print("=== Running server throughput benchmarks")
	print("modes:")
	for mode in modes:
		print(f"  - {mode}: {MODE_LABELS[mode]}")
	print()
	print("name\tstatus\tnote\t" + "\t".join(modes))
	failures = 0
	for bench in SERVERS:
		status, cells, note = run_server_bench(bench, env, host, port, requests, concurrency, modes)
		row = [bench.name, status, note]
		row.extend(cells[mode] for mode in modes)
		print("\t".join(row))
		if status == "ERR":
			failures += 1
	print("=== End server throughput benchmarks")
	return 1 if failures else 0


def main() -> int:
	parser = argparse.ArgumentParser(description="Run all project benchmarks")
	parser.add_argument("--fast", action="store_true", help="Use lower iteration counts")
	parser.add_argument("--core-only", action="store_true", help="Skip server throughput suite")
	parser.add_argument("--requests", type=int, default=10_000, help="Requests per server benchmark")
	parser.add_argument("--concurrency", type=int, default=100, help="Concurrency for load tools")
	parser.add_argument("--host", default="localhost", help="Benchmark host")
	parser.add_argument("--port", type=int, default=8000, help="Benchmark port")
	parser.add_argument(
		"--modes",
		default="all",
		help="Comma-separated server benchmark modes or 'all'",
	)
	args = parser.parse_args()
	try:
		modes = parse_modes(args.modes)
	except ValueError as err:
		print(f"ERR {err}")
		return 2

	env = mk_env()
	env["HTTP_PORT"] = str(args.port)
	env["UVICORN_HOST"] = "0.0.0.0"

	if args.fast:
		core_label = "fast"
		routing_args = [
			"--iterations",
			"10000",
			"--warmup",
			"1000",
			"--static-routes",
			"200",
			"--param-routes",
			"200",
			"--sample-size",
			"256",
		]
		reqres_args = [
			"--iterations",
			"10000",
			"--warmup",
			"1000",
			"--sample-size",
			"128",
		]
	else:
		core_label = "baseline"
		routing_args = [
			"--iterations",
			"100000",
			"--warmup",
			"10000",
			"--static-routes",
			"500",
			"--param-routes",
			"500",
			"--sample-size",
			"512",
		]
		reqres_args = [
			"--iterations",
			"100000",
			"--warmup",
			"10000",
			"--sample-size",
			"256",
		]

	core_result = run_core(core_label, routing_args, reqres_args, env)
	if core_result != 0:
		return core_result

	if args.core_only:
		return 0

	return run_server_suite(env, args.requests, args.concurrency, args.host, args.port, modes)


if __name__ == "__main__":
	raise SystemExit(main())


# EOF
