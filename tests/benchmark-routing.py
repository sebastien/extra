#!/usr/bin/env python3
import argparse
import gc
import os
import random
import statistics
from time import perf_counter_ns

import extra.routing as routing
from extra.routing import Dispatcher, Handler


def _quiet_info(*args, **kwargs):
	return None


def pin_cpu() -> None:
	"""Pin to one core when possible to cut scheduler noise."""
	try:
		os.sched_setaffinity(0, {0})
	except (AttributeError, OSError, ValueError):
		pass


routing.info = _quiet_info


def noop(request, **params):
	return None


def build_dispatcher(static_routes: int, param_routes: int) -> Dispatcher:
	dispatcher = Dispatcher()
	for i in range(static_routes):
		handler = Handler(noop, methods=[("GET", f"/static/{i}")])
		dispatcher.register(handler)
	for i in range(param_routes):
		handler = Handler(
			noop, methods=[("GET", f"/users/{i}/{{id:int}}/{{slug:name}}")]
		)
		dispatcher.register(handler)
	dispatcher.prepare()
	return dispatcher


def calibrate_iterations(
	dispatcher: Dispatcher,
	paths: list[str],
	target_ms: float,
	floor: int,
	ceiling: int,
) -> int:
	"""Pick iterations so one timed round lasts about target_ms."""
	n = len(paths)
	probe = min(max(floor // 10, 1_000), ceiling)
	for i in range(probe):
		dispatcher.match("GET", paths[i % n])
	start = perf_counter_ns()
	for i in range(probe):
		dispatcher.match("GET", paths[i % n])
	elapsed = perf_counter_ns() - start
	if elapsed <= 0:
		return floor
	nsOp = elapsed / probe
	targetNs = target_ms * 1_000_000.0
	scaled = int(targetNs / nsOp) if nsOp else floor
	return max(floor, min(ceiling, scaled))


def stable_elapsed(samples: list[int]) -> int:
	"""Median after dropping min/max when enough rounds (thermal noise is one-sided)."""
	if len(samples) >= 5:
		trimmed = sorted(samples)[1:-1]
		return int(statistics.median(trimmed))
	return int(statistics.median(samples))


def bench_match(
	dispatcher: Dispatcher,
	paths: list[str],
	iterations: int,
	warmup: int,
	rounds: int,
) -> tuple[int, int, list[int]]:
	"""Returns (stable elapsed ns, hits, all sample elapsed ns)."""
	n = len(paths)
	for i in range(warmup):
		dispatcher.match("GET", paths[i % n])
	samples: list[int] = []
	hits = 0
	gc.collect()
	wasEnabled = gc.isenabled()
	gc.disable()
	try:
		for _ in range(rounds):
			roundHits = 0
			start = perf_counter_ns()
			for i in range(iterations):
				route, _ = dispatcher.match("GET", paths[i % n])
				if route is not None:
					roundHits += 1
			samples.append(perf_counter_ns() - start)
			hits = roundHits
	finally:
		if wasEnabled:
			gc.enable()
	return stable_elapsed(samples), hits, samples


def print_result(
	name: str,
	iterations: int,
	elapsed_ns: int,
	hits: int,
	samples: list[int],
) -> None:
	nsOp = elapsed_ns / iterations
	opsS = iterations * 1_000_000_000 / elapsed_ns if elapsed_ns else 0.0
	spread = 0.0
	if samples and elapsed_ns:
		# Spread over the same trimmed window used for the reported value
		core = sorted(samples)[1:-1] if len(samples) >= 5 else samples
		lo = min(core) / iterations
		hi = max(core) / iterations
		spread = (hi - lo) / nsOp * 100.0 if nsOp else 0.0
	print(
		f"{name:12} ops={iterations:9d} time={elapsed_ns / 1_000_000:10.3f}ms "
		f"ns/op={nsOp:10.1f} ops/s={opsS:12.1f} hits={hits:9d} "
		f"spread={spread:4.1f}%"
	)


def main() -> None:
	parser = argparse.ArgumentParser(description="Core routing benchmark")
	parser.add_argument("--static-routes", type=int, default=500)
	parser.add_argument("--param-routes", type=int, default=500)
	parser.add_argument(
		"--iterations",
		type=int,
		default=0,
		help="Fixed iterations per round (0 = auto-calibrate to --target-ms)",
	)
	parser.add_argument("--warmup", type=int, default=20_000)
	parser.add_argument("--sample-size", type=int, default=512)
	parser.add_argument(
		"--rounds",
		type=int,
		default=7,
		help="Timed rounds per scenario; report median (reduces noise)",
	)
	parser.add_argument(
		"--target-ms",
		type=float,
		default=400.0,
		help="Target wall time per round when --iterations=0",
	)
	parser.add_argument("--min-iterations", type=int, default=20_000)
	parser.add_argument("--max-iterations", type=int, default=2_000_000)
	args = parser.parse_args()
	pin_cpu()

	dispatcher = build_dispatcher(args.static_routes, args.param_routes)

	staticHits = [f"/static/{i % args.static_routes}" for i in range(args.sample_size)]
	paramHits = [
		f"/users/{i % args.param_routes}/{(i * 7) % 10_000}/post-{i}"
		for i in range(args.sample_size)
	]
	misses = [f"/missing/{i}/path" for i in range(args.sample_size)]
	mixed = list(staticHits) + list(paramHits) + list(misses)
	random.Random(42).shuffle(mixed)

	scenarios = (
		("static-hit", staticHits),
		("param-hit", paramHits),
		("miss", misses),
		("mixed", mixed),
	)

	print(
		"benchmark-routing "
		f"static_routes={args.static_routes} "
		f"param_routes={args.param_routes} "
		f"warmup={args.warmup} rounds={args.rounds} "
		f"target_ms={args.target_ms if args.iterations <= 0 else 'fixed'}"
	)

	for name, paths in scenarios:
		iterations = args.iterations
		if iterations <= 0:
			iterations = calibrate_iterations(
				dispatcher,
				paths,
				args.target_ms,
				args.min_iterations,
				args.max_iterations,
			)
		elapsed, hits, samples = bench_match(
			dispatcher, paths, iterations, args.warmup, args.rounds
		)
		print_result(name, iterations, elapsed, hits, samples)


if __name__ == "__main__":
	main()


# EOF
