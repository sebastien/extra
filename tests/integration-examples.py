from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"
EXPECT_PATTERN = re.compile(r"^\s*#\s*EXPECT:\s*(.+?)\s*$")
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


def extract_expected_lines(path: Path) -> list[str]:
	expected: list[str] = []
	for line in path.read_text(encoding="utf-8").splitlines():
		match = EXPECT_PATTERN.match(line)
		if match:
			expected.append(match.group(1))
	return expected


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
	expected = extract_expected_lines(path)
	mode = "daemon" if path.name in DAEMON_EXAMPLES else "finite"
	if not expected:
		return RunResult(
			name=path.name,
			mode=mode,
			timeout=0,
			returncode=None,
			timed_out=False,
			killed=False,
			output="",
			expected=[],
			missing=["No # EXPECT: lines found"],
		)

	timeout = TIMEOUTS.get(path.name, DEFAULT_TIMEOUT)
	env = os.environ.copy()
	env["PYTHONUNBUFFERED"] = "1"
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

	timed_out = False
	killed = False
	try:
		output, _ = process.communicate(timeout=timeout)
	except subprocess.TimeoutExpired:
		if mode == "daemon":
			killed = True
			process.terminate()
			try:
				output, _ = process.communicate(timeout=2.0)
			except subprocess.TimeoutExpired:
				process.kill()
				output, _ = process.communicate()
		else:
			timed_out = True
			process.kill()
			output, _ = process.communicate()

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
			has_runtime_failure = result.returncode is not None and result.returncode != 0
		elif not result.killed:
			has_runtime_failure = result.returncode is not None and result.returncode != 0
		is_failure = bool(result.missing) or has_runtime_failure
		status = "FAIL" if is_failure else "PASS"
		if result.timed_out:
			detail = "timeout"
		elif result.killed:
			detail = "killed"
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
