#!/usr/bin/env python3
import argparse
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
SRC_PY = ROOT / "src" / "py"
PURE_PY = ROOT / ".run" / "bench-pure" / "py"
MYPYC_MARKER_MODULES = (
	"extra/routing",
	"extra/model",
	"extra/http/parser",
)

RPS_AB_RE = re.compile(r"Requests per second:\s+([\d\.]+)")
RPS_H2_RE = re.compile(r"finished in .*?,\s*([\d\.]+)\s*req/s")
CORE_ROW_RE = re.compile(
	r"^(?P<name>[\w\-]+)\s+ops=\s*(?P<ops>\d+)\s+time=\s*(?P<time>[\d\.]+)ms\s+"
	r"ns/op=\s*(?P<nsop>[\d\.]+)\s+ops/s=\s*(?P<opss>[\d\.]+)"
	r"(?:\s+hits=\s*(?P<hits>\d+))?"
	r"(?:\s+spread=\s*(?P<spread>[\d\.]+)%)?"
)

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

MODE_SHORT: dict[str, str] = {
	"h10_close_legacy": "h10-close",
	"h10_keepalive_legacy": "h10-ka",
	"h1_close": "h1-close",
	"h1_keepalive_serial": "h1-ka",
	"h1_keepalive_pipeline": "h1-pipe",
}

MODE_TOOLS: dict[str, str] = {
	"h10_close_legacy": "ab",
	"h10_keepalive_legacy": "ab",
	"h1_close": "h2load",
	"h1_keepalive_serial": "h2load",
	"h1_keepalive_pipeline": "h2load",
}

# Preferred mode for the end summary when available
SUMMARY_MODE = "h1_keepalive_serial"


@dataclass(frozen=True)
class ServerBench:
	name: str
	command: tuple[str, ...]
	# Optional PYTHONPATH override (absolute). None → default env path.
	pythonPath: str | None = None
	# If set, skip unless this kind of build is available.
	requires: str | None = None  # "mypyc" | None


@dataclass
class CoreRow:
	name: str
	ops: int
	nsOp: float
	opsS: float
	spread: float | None


@dataclass
class ServerRow:
	name: str
	status: str
	note: str
	cells: dict[str, str] = field(default_factory=dict)


def ext_suffix() -> str:
	import sysconfig

	return sysconfig.get_config_var("EXT_SUFFIX") or ".so"


def materialize_pure_tree() -> Path:
	"""Copy only .py sources so pure-Python imports never pick up sibling .so files."""
	destRoot = PURE_PY
	if destRoot.exists():
		shutil.rmtree(destRoot)
	destRoot.mkdir(parents=True, exist_ok=True)
	for src in SRC_PY.rglob("*.py"):
		rel = src.relative_to(SRC_PY)
		dest = destRoot / rel
		dest.parent.mkdir(parents=True, exist_ok=True)
		shutil.copy2(src, dest)
	return destRoot


def mypyc_so_paths() -> list[Path]:
	suffix = ext_suffix()
	found: list[Path] = []
	for mod in MYPYC_MARKER_MODULES:
		path = SRC_PY / f"{mod}{suffix}"
		if path.is_file():
			found.append(path)
	return found


def probe_mypyc_import(pythonpath: str) -> tuple[bool, str]:
	"""Return (ok, detail) after checking import + compiled routing module."""
	code = (
		"import extra.routing as r, extra.server as s; "
		"f=r.__file__ or ''; "
		"print(f); "
		"print('COMPILED' if f.endswith('.so') or '.so' in f else 'PURE')"
	)
	env = dict(os.environ)
	env["PYTHONPATH"] = pythonpath
	env["EXTRA_LOG_REQUESTS"] = "0"
	try:
		result = subprocess.run(
			[sys.executable, "-c", code],
			env=env,
			check=False,
			capture_output=True,
			text=True,
			timeout=30,
		)
	except subprocess.TimeoutExpired:
		return False, "import timeout"
	if result.returncode != 0:
		err = (result.stderr or result.stdout or "import failed").strip().splitlines()
		return False, err[-1] if err else "import failed"
	lines = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
	if not lines:
		return False, "empty import probe"
	if lines[-1] != "COMPILED":
		return False, f"routing not compiled ({lines[-1]})"
	return True, lines[0]


def ensure_mypyc(auto_compile: bool = True) -> tuple[bool, str]:
	"""Ensure mypyc artifacts exist and import cleanly. Returns (ok, note)."""
	# Drop extensions for modules that must stay pure (user subclasses / ABC)
	_purge_pure_module_sos()

	ok, detail = probe_mypyc_import(str(SRC_PY))
	if ok:
		return True, detail

	if not auto_compile:
		return False, detail

	print("  … compiling extra with mypyc (setup.py build_ext --use-mypyc)", flush=True)
	(ROOT / "build").mkdir(parents=True, exist_ok=True)
	compile_cmd = [
		sys.executable,
		str(ROOT / "setup.py"),
		"build_ext",
		"--inplace",
		"--use-mypyc",
	]
	# Prefer uv run so mypy/mypyc is available
	uv = shutil.which("uv")
	if uv:
		compile_cmd = [
			uv,
			"run",
			"--with",
			"mypy",
			"python",
			str(ROOT / "setup.py"),
			"build_ext",
			"--inplace",
			"--use-mypyc",
		]
	try:
		result = subprocess.run(
			compile_cmd,
			cwd=str(ROOT),
			check=False,
			capture_output=True,
			text=True,
			timeout=600,
			env={
				**os.environ,
				"UV_CACHE_DIR": str(ROOT / ".run" / "uv-cache"),
			},
		)
	except subprocess.TimeoutExpired:
		return False, "mypyc compile timeout"
	if result.returncode != 0:
		tail = (result.stderr or result.stdout or "").strip().splitlines()
		msg = tail[-1] if tail else f"compile rc={result.returncode}"
		return False, msg

	_purge_pure_module_sos()

	ok, detail = probe_mypyc_import(str(SRC_PY))
	if ok:
		return True, detail
	return False, detail or "mypyc probe failed after compile"


def _purge_pure_module_sos() -> None:
	"""Remove .so for modules excluded from mypyc so pure .py is used."""
	patterns = (
		"extra/server.cpython-*.so",
		"extra/model.cpython-*.so",
		"extra/http/api.cpython-*.so",
		"extra/http/model.cpython-*.so",
		"extra/client.cpython-*.so",
	)
	for pattern in patterns:
		for stale in SRC_PY.glob(pattern):
			try:
				stale.unlink()
			except OSError:
				pass


def mk_env(pythonpath: str | None = None) -> dict[str, str]:
	env = dict(os.environ)
	base = pythonpath if pythonpath is not None else str(SRC_PY)
	existing = env.get("PYTHONPATH", "")
	env["PYTHONPATH"] = f"{base}:{existing}" if existing else base
	# Prefer the same interpreter for nested python/bash scripts
	env["PYTHON"] = sys.executable
	return env


def parse_core_output(text: str) -> list[CoreRow]:
	rows: list[CoreRow] = []
	for line in text.splitlines():
		match = CORE_ROW_RE.search(line.strip())
		if not match:
			continue
		spread = match.group("spread")
		rows.append(
			CoreRow(
				name=match.group("name"),
				ops=int(match.group("ops")),
				nsOp=float(match.group("nsop")),
				opsS=float(match.group("opss")),
				spread=float(spread) if spread is not None else None,
			)
		)
	return rows


def print_core_table(title: str, rows: list[CoreRow]) -> None:
	print(title)
	print("+------------+-----------+------------+-------------+----------+")
	print("| scenario   | ops       | ns/op      | ops/s       | spread   |")
	print("+------------+-----------+------------+-------------+----------+")
	for row in rows:
		spreadText = f"{row.spread:6.1f}%" if row.spread is not None else "     n/a"
		print(
			f"| {row.name:<10} | {row.ops:>9d} | {row.nsOp:>10.1f} | "
			f"{row.opsS:>11.1f} | {spreadText:>8} |"
		)
	print("+------------+-----------+------------+-------------+----------+")


def print_server_table(modes: tuple[str, ...], rows: list[ServerRow]) -> None:
	shorts = [MODE_SHORT.get(mode, mode) for mode in modes]
	# Column widths
	nameW = max(10, max((len(r.name) for r in rows), default=10))
	statusW = 6
	modeW = max(10, max((len(s) for s in shorts), default=10))
	noteW = 24

	def line(parts: list[str], widths: list[int]) -> str:
		cells = [f" {p:<{w}} " for p, w in zip(parts, widths)]
		return "|" + "|".join(cells) + "|"

	def rule(widths: list[int]) -> str:
		return "+" + "+".join("-" * (w + 2) for w in widths) + "+"

	widths = [nameW, statusW, *[modeW for _ in modes], noteW]
	headers = ["server", "status", *shorts, "note"]
	print("Server Throughput")
	print(rule(widths))
	print(line(headers, widths))
	print(rule(widths))
	for row in rows:
		cells = [row.name, row.status]
		for mode in modes:
			cells.append(row.cells.get(mode, "-"))
		note = row.note if row.note else ""
		if len(note) > noteW:
			note = note[: noteW - 1] + "…"
		cells.append(note)
		print(line(cells, widths))
	print(rule(widths))


def print_summary(
	routing: list[CoreRow],
	reqres: list[CoreRow],
	serverRows: list[ServerRow] | None,
	modes: tuple[str, ...],
	skipped: str | None,
) -> None:
	print()
	print("=== Benchmark Summary ===")
	print("Core (ns/op, lower is better):")
	for section, rows in (("routing", routing), ("reqres", reqres)):
		for row in rows:
			spread = f"  spread {row.spread:.1f}%" if row.spread is not None else ""
			print(f"  {section:8} {row.name:<12} {row.nsOp:>10.1f} ns/op{spread}")

	if skipped:
		print(f"Server: skipped ({skipped})")
		return

	if not serverRows:
		print("Server: (not run)")
		return

	print("Server (req/s, higher is better):")
	summaryMode = (
		SUMMARY_MODE if SUMMARY_MODE in modes else (modes[0] if modes else None)
	)
	if summaryMode:
		print(
			f"  mode: {MODE_SHORT.get(summaryMode, summaryMode)} — {MODE_LABELS[summaryMode]}"
		)
	for row in serverRows:
		if row.status == "SKIP":
			print(f"  {row.name:<12} SKIP  {row.note}")
			continue
		if summaryMode:
			cell = row.cells.get(summaryMode, "-")
			print(f"  {row.name:<12} {cell:>12} req/s  [{row.status}]")
		else:
			print(f"  {row.name:<12} [{row.status}]")
	# Best OK server by summary mode if numeric
	if summaryMode:
		bestName = None
		bestRps = -1.0
		for row in serverRows:
			if row.status == "SKIP":
				continue
			raw = row.cells.get(summaryMode, "")
			try:
				value = float(raw.rstrip("*").split()[0])
			except (ValueError, IndexError):
				continue
			if value > bestRps:
				bestRps = value
				bestName = row.name
		if bestName is not None:
			print(f"  best: {bestName} @ {bestRps:,.1f} req/s")


def run_core(
	label: str, routing_args: list[str], reqres_args: list[str], env: dict[str, str]
) -> tuple[int, list[CoreRow], list[CoreRow]]:
	print(f"=== Running core benchmarks ({label})", flush=True)
	with (
		tempfile.NamedTemporaryFile(mode="wt", delete=False) as routing_out,
		tempfile.NamedTemporaryFile(mode="wt", delete=False) as reqres_out,
	):
		routing_path = routing_out.name
		reqres_path = reqres_out.name
	try:
		routing_cmd = [
			sys.executable,
			str(TESTS / "benchmark-routing.py"),
			*routing_args,
		]
		reqres_cmd = [sys.executable, str(TESTS / "benchmark-reqres.py"), *reqres_args]
		routing_result = subprocess.run(
			routing_cmd,
			env=env,
			check=False,
			stdout=subprocess.PIPE,
			stderr=subprocess.STDOUT,
			text=True,
		)
		if routing_result.returncode != 0:
			print(routing_result.stdout.rstrip())
			print("ERR benchmark-routing failed")
			return routing_result.returncode, [], []
		Path(routing_path).write_text(routing_result.stdout, encoding="utf8")
		routing_rows = parse_core_output(routing_result.stdout)

		reqres_result = subprocess.run(
			reqres_cmd,
			env=env,
			check=False,
			stdout=subprocess.PIPE,
			stderr=subprocess.STDOUT,
			text=True,
		)
		if reqres_result.returncode != 0:
			print(reqres_result.stdout.rstrip())
			print("ERR benchmark-reqres failed")
			return reqres_result.returncode, routing_rows, []
		Path(reqres_path).write_text(reqres_result.stdout, encoding="utf8")
		reqres_rows = parse_core_output(reqres_result.stdout)

		print_core_table(f"Routing {label.capitalize()}", routing_rows)
		print()
		print_core_table(f"ReqRes {label.capitalize()}", reqres_rows)
		return 0, routing_rows, reqres_rows
	finally:
		for path in (routing_path, reqres_path):
			if Path(path).exists():
				Path(path).unlink()


def wait_for_port(host: str, port: int, timeout: float = 10.0) -> bool:
	# Try IPv4 loopback first when host is a wildcard / localhost alias
	candidates = []
	if host in ("localhost", "0.0.0.0", "::"):
		candidates.extend(["127.0.0.1", "localhost"])
	else:
		candidates.append(host)
	deadline = time.monotonic() + timeout
	while time.monotonic() < deadline:
		for target in candidates:
			try:
				with socket.create_connection((target, port), timeout=0.5):
					return True
			except OSError:
				continue
		time.sleep(0.1)
	return False


def free_port(host: str, preferred: int) -> int:
	"""Return preferred if free, else bind an ephemeral port."""
	try:
		with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
			sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
			sock.bind((host if host != "localhost" else "127.0.0.1", preferred))
			return preferred
	except OSError:
		with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
			sock.bind((host if host != "localhost" else "127.0.0.1", 0))
			return int(sock.getsockname()[1])


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


def build_mode_command(
	mode: str, host: str, port: int, requests: int, concurrency: int
) -> list[str]:
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
	timeout: float = 60.0,
) -> tuple[str, bool]:
	# Prefer IPv4 loopback — servers bind 0.0.0.0; "localhost" may hit ::1 first.
	loadHost = "127.0.0.1" if host in ("localhost", "0.0.0.0", "::") else host
	cmd = build_mode_command(mode, loadHost, port, requests, concurrency)
	try:
		result = subprocess.run(
			cmd,
			env=env,
			check=False,
			capture_output=True,
			text=True,
			timeout=timeout,
		)
	except subprocess.TimeoutExpired:
		return ("ERR timeout", False)
	output = f"{result.stdout}\n{result.stderr}"
	rps = parse_mode_rps(mode, output)
	if not rps:
		if result.returncode != 0:
			return (f"ERR rc={result.returncode}", False)
		return ("ERR parse", False)
	if result.returncode != 0:
		return (f"{rps}*", False)
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
) -> ServerRow:
	benchEnv = dict(env)
	if bench.pythonPath is not None:
		existing = benchEnv.get("PYTHONPATH", "")
		# Put override first so it wins over any ambient path
		benchEnv["PYTHONPATH"] = (
			f"{bench.pythonPath}:{existing}" if existing else bench.pythonPath
		)

	# Capture early startup errors without risking a full pipe deadlock under load.
	# (stderr=PIPE + high request logging fills the OS pipe and freezes the server.)
	errPath = tempfile.NamedTemporaryFile(
		mode="w+", delete=False, prefix=f"bench-{bench.name}-", suffix=".err"
	)
	errPath.close()
	try:
		with open(errPath.name, "w", encoding="utf8") as errFile:
			proc = subprocess.Popen(
				list(bench.command),
				env=benchEnv,
				stdout=subprocess.DEVNULL,
				stderr=errFile,
				text=True,
			)
			try:
				if not wait_for_port(host, port):
					stop_process(proc)
					note = ""
					try:
						note = Path(errPath.name).read_text(encoding="utf8").strip()
					except OSError:
						note = ""
					msg = note.splitlines()[-1] if note else "server did not start"
					return ServerRow(
						name=bench.name,
						status="SKIP",
						note=msg,
						cells={mode: "-" for mode in modes},
					)

				cells: dict[str, str] = {}
				failures = 0
				for mode in modes:
					cell, ok = run_mode(mode, env, host, port, requests, concurrency)
					cells[mode] = cell
					if not ok:
						failures += 1
				status = (
					"OK"
					if failures == 0
					else ("WARN" if failures < len(modes) else "ERR")
				)
				return ServerRow(name=bench.name, status=status, note="", cells=cells)
			finally:
				stop_process(proc)
	finally:
		try:
			Path(errPath.name).unlink(missing_ok=True)
		except OSError:
			pass


def build_server_list(mypyc_ok: bool, pure_path: Path) -> list[ServerBench]:
	"""extra-aio (pure) first, then extra-aio-mypyc when available, then baselines."""
	extraCmd = (sys.executable, str(TESTS / "benchmark-extra-aio.py"))
	servers: list[ServerBench] = [
		ServerBench("extra-aio", extraCmd, pythonPath=str(pure_path)),
	]
	if mypyc_ok:
		servers.append(
			ServerBench(
				"extra-aio-mypyc",
				extraCmd,
				pythonPath=str(SRC_PY),
				requires="mypyc",
			)
		)
	servers.extend(
		[
			ServerBench("socket", (sys.executable, str(TESTS / "benchmark-socket.py"))),
			ServerBench(
				"aiosocket",
				(sys.executable, str(TESTS / "benchmark-aiosocket.py")),
			),
			ServerBench(
				"aioserver",
				(sys.executable, str(TESTS / "benchmark-aioserver.py")),
			),
			ServerBench(
				"aiohttp", (sys.executable, str(TESTS / "benchmark-aiohttp.py"))
			),
			ServerBench("raw-asgi", ("bash", str(TESTS / "benchmark-raw.sh"))),
			ServerBench("fastapi", ("bash", str(TESTS / "benchmark-fastapi.sh"))),
		]
	)
	return servers


def run_server_suite(
	env: dict[str, str],
	requests: int,
	concurrency: int,
	host: str,
	port: int,
	modes: tuple[str, ...],
	*,
	auto_compile: bool = True,
) -> tuple[int, list[ServerRow], str | None]:
	required = sorted({MODE_TOOLS[mode] for mode in modes})
	missing = [cmd for cmd in required if shutil.which(cmd) is None]
	if missing:
		msg = f"missing tools: {', '.join(missing)}"
		print(f"=== Server benchmark suite skipped ({msg})")
		return 0, [], msg

	print()
	print("=== Preparing pure / mypyc trees")
	pure_path = materialize_pure_tree()
	print(f"  pure:  {pure_path}")
	mypyc_ok, mypyc_note = ensure_mypyc(auto_compile=auto_compile)
	if mypyc_ok:
		print(f"  mypyc: OK ({mypyc_note})")
	else:
		print(f"  mypyc: SKIP ({mypyc_note})")
		print("         tip: make compile   # build mypyc extensions in-place")

	servers = build_server_list(mypyc_ok, pure_path)

	print()
	print("=== Running server throughput benchmarks")
	print("modes:")
	for mode in modes:
		print(f"  - {MODE_SHORT.get(mode, mode)}: {MODE_LABELS[mode]}")
	print(f"requests={requests} concurrency={concurrency} host={host} port={port}")
	print()

	rows: list[ServerRow] = []
	failures = 0
	for bench in servers:
		print(f"  … {bench.name}", flush=True)
		row = run_server_bench(bench, env, host, port, requests, concurrency, modes)
		rows.append(row)
		if row.status == "ERR":
			failures += 1
	if not mypyc_ok:
		rows.insert(
			1,
			ServerRow(
				name="extra-aio-mypyc",
				status="SKIP",
				note=mypyc_note,
				cells={mode: "-" for mode in modes},
			),
		)
	print()
	print_server_table(modes, rows)
	return (1 if failures else 0), rows, None


def main() -> int:
	parser = argparse.ArgumentParser(description="Run all project benchmarks")
	parser.add_argument(
		"--fast", action="store_true", help="Faster core + lighter server load"
	)
	parser.add_argument(
		"--core-only", action="store_true", help="Skip server throughput suite"
	)
	parser.add_argument(
		"--requests", type=int, default=0, help="Requests per server mode (0 = default)"
	)
	parser.add_argument(
		"--concurrency",
		type=int,
		default=0,
		help="Load-tool concurrency (0 = default)",
	)
	parser.add_argument("--host", default="localhost", help="Benchmark host")
	parser.add_argument("--port", type=int, default=8000, help="Benchmark port")
	parser.add_argument(
		"--modes",
		default="all",
		help="Comma-separated server benchmark modes or 'all'",
	)
	parser.add_argument(
		"--no-compile",
		action="store_true",
		help="Do not auto-run mypyc compile; skip extra-aio-mypyc if missing",
	)
	args = parser.parse_args()
	try:
		modes = parse_modes(args.modes)
	except ValueError as err:
		print(f"ERR {err}")
		return 2

	# Default env uses pure tree for core microbenches (stable, no stale .so)
	pure_path = materialize_pure_tree()
	env = mk_env(str(pure_path))
	port = free_port(args.host, args.port)
	# Server scripts use HTTP_PORT; extra.run uses PORT from config
	env["HTTP_PORT"] = str(port)
	env["PORT"] = str(port)
	env["UVICORN_HOST"] = "0.0.0.0"
	env["UVICORN_PORT"] = str(port)
	# Avoid request-log spam during load tests (also prevents pipe deadlocks)
	env["EXTRA_LOG_REQUESTS"] = "0"

	if args.fast:
		core_label = "fast"
		routing_args = [
			"--warmup",
			"2000",
			"--static-routes",
			"200",
			"--param-routes",
			"200",
			"--sample-size",
			"256",
			"--rounds",
			"3",
			"--target-ms",
			"100",
		]
		reqres_args = [
			"--warmup",
			"2000",
			"--sample-size",
			"128",
			"--rounds",
			"3",
			"--target-ms",
			"100",
		]
		requests = args.requests or 2_000
		concurrency = args.concurrency or 50
	else:
		core_label = "baseline"
		routing_args = [
			"--warmup",
			"20000",
			"--static-routes",
			"500",
			"--param-routes",
			"500",
			"--sample-size",
			"512",
			"--rounds",
			"7",
			"--target-ms",
			"300",
		]
		reqres_args = [
			"--warmup",
			"15000",
			"--sample-size",
			"256",
			"--rounds",
			"7",
			"--target-ms",
			"300",
		]
		requests = args.requests or 10_000
		concurrency = args.concurrency or 100

	core_rc, routing_rows, reqres_rows = run_core(
		core_label, routing_args, reqres_args, env
	)
	if core_rc != 0:
		return core_rc

	server_rows: list[ServerRow] | None = None
	skipped: str | None = None
	server_rc = 0
	if args.core_only:
		skipped = "core-only"
	else:
		server_rc, server_rows, skipped = run_server_suite(
			env,
			requests,
			concurrency,
			args.host,
			port,
			modes,
			auto_compile=not args.no_compile,
		)

	print_summary(routing_rows, reqres_rows, server_rows, modes, skipped)
	return server_rc


if __name__ == "__main__":
	raise SystemExit(main())


# EOF
