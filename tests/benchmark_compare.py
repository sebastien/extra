#!/usr/bin/env python3
"""Modular benchmark comparison runner.

Usage:
	python tests/benchmark_compare.py [--level routing|reqres|server|all]
"""

import argparse
import shutil
import sys

import benchmark_compare_extra as extra_backend
import benchmark_compare_fastapi as fastapi_backend
from benchmark_compare_common import (
	MODE_LABELS,
	parse_modes,
	print_comparison,
	print_header,
	required_tools_for_modes,
)


def run_routing(args: argparse.Namespace) -> None:
	print_header("Level 1: Routing-Only Benchmark")
	print(
		f"routes: {args.static_routes} static + {args.param_routes} param, "
		f"iterations: {args.iterations}, warmup: {args.warmup}"
	)
	print()

	print("--- Extra ---")
	extra_results = extra_backend.run_routing(args)

	print()
	print("--- Starlette ---")
	starlette_results = fastapi_backend.run_routing(args)

	print()
	print("--- Comparison (ns/op) ---")
	for scenario in extra_results:
		print_comparison(
			scenario, extra_results[scenario], starlette_results[scenario], "Starlette"
		)


def run_reqres(args: argparse.Namespace) -> None:
	print_header("Level 2: Request/Response Pipeline Benchmark")
	print(f"iterations: {args.iterations}, warmup: {args.warmup}")
	print()

	print("--- Extra (routing + handler + head serialisation) ---")
	extra_results = extra_backend.run_reqres(args)

	print()
	print("--- Starlette Router (routing + handler + ASGI send, no FastAPI) ---")
	starlette_results, fastapi_results = fastapi_backend.run_reqres(args)

	print()
	print("--- Comparison: Extra vs Starlette Router (ns/op) ---")
	for scenario in extra_results:
		print_comparison(
			scenario, extra_results[scenario], starlette_results[scenario], "Starlette"
		)

	print()
	print("--- Comparison: Extra vs FastAPI full-stack (ns/op) ---")
	for scenario in extra_results:
		print_comparison(
			scenario, extra_results[scenario], fastapi_results[scenario], "FastAPI"
		)


def run_server(args: argparse.Namespace) -> None:
	print_header("Level 3: Server Throughput Benchmark")
	missing = [
		tool
		for tool in required_tools_for_modes(args.server_modes)
		if not shutil.which(tool)
	]
	if missing:
		print(f"  SKIP: missing tools: {', '.join(missing)}")
		return

	print(
		f"requests: {args.server_requests}, concurrency: {args.server_concurrency}, port: {args.port}"
	)
	print("modes:")
	for mode in args.server_modes:
		print(f"  - {mode}: {MODE_LABELS[mode]}")
	print()

	print("--- Extra ---")
	extra_rps = extra_backend.run_server(args, args.server_modes)
	if extra_rps is None:
		print("  extra: SKIP")
	else:
		for mode in args.server_modes:
			value = extra_rps.get(mode)
			print(f"  {mode:24} {'ERR' if value is None else f'{value:,.1f} req/s'}")

	print()
	print("--- FastAPI (uvicorn) ---")
	fastapi_rps = fastapi_backend.run_server(args, args.server_modes)
	if fastapi_rps is None:
		print("  fastapi: SKIP")
	else:
		for mode in args.server_modes:
			value = fastapi_rps.get(mode)
			print(f"  {mode:24} {'ERR' if value is None else f'{value:,.1f} req/s'}")

	if extra_rps and fastapi_rps:
		print()
		print("--- Comparison (req/s) ---")
		for mode in args.server_modes:
			extra_val = extra_rps.get(mode)
			fastapi_val = fastapi_rps.get(mode)
			if extra_val is None or fastapi_val is None or fastapi_val <= 0:
				print(f"  {mode:24} comparison unavailable")
				continue
			ratio = extra_val / fastapi_val
			if ratio >= 1:
				print(
					f"  {mode:24} Extra is {ratio:.2f}x faster ({extra_val:,.1f} vs {fastapi_val:,.1f})"
				)
			else:
				print(
					f"  {mode:24} FastAPI is {1 / ratio:.2f}x faster ({extra_val:,.1f} vs {fastapi_val:,.1f})"
				)


def main() -> None:
	parser = argparse.ArgumentParser(
		description="Comparative benchmark: Extra vs FastAPI/Starlette"
	)
	parser.add_argument(
		"--level",
		choices=["routing", "reqres", "server", "all"],
		default="all",
		help="Which benchmark level to run (default: all)",
	)
	parser.add_argument("--iterations", type=int, default=100_000)
	parser.add_argument("--warmup", type=int, default=10_000)
	parser.add_argument("--sample-size", type=int, default=256)
	parser.add_argument("--static-routes", type=int, default=50)
	parser.add_argument("--param-routes", type=int, default=50)
	parser.add_argument("--port", type=int, default=8000)
	parser.add_argument("--server-requests", type=int, default=10_000)
	parser.add_argument("--server-concurrency", type=int, default=100)
	parser.add_argument(
		"--server-modes",
		default="all",
		help="Comma-separated server benchmark modes or 'all'",
	)
	parser.add_argument(
		"--fast", action="store_true", help="Reduce iterations for quick check"
	)
	args = parser.parse_args()

	try:
		args.server_modes = parse_modes(args.server_modes)
	except ValueError as err:
		print(f"ERROR: {err}")
		sys.exit(2)

	if args.fast:
		args.iterations = 10_000
		args.warmup = 1_000
		args.server_requests = 2_000

	try:
		fastapi_backend.ensure_available()
	except RuntimeError as err:
		print(f"ERROR: {err}")
		sys.exit(1)

	print("=" * 72)
	print("  Benchmark Compare: Extra vs FastAPI/Starlette")
	print("=" * 72)

	if args.level in ("routing", "all"):
		run_routing(args)

	if args.level in ("reqres", "all"):
		run_reqres(args)

	if args.level in ("server", "all"):
		run_server(args)

	print()
	print("Done.")


if __name__ == "__main__":
	main()


# EOF
