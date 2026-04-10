#!/usr/bin/env python3
import argparse
import random
from time import perf_counter_ns

import extra.routing as routing
from extra.routing import Dispatcher, Handler


def _quiet_info(*args, **kwargs):
	return None


routing.info = _quiet_info


def noop(request, **params):
	return None


def build_dispatcher(static_routes: int, param_routes: int) -> Dispatcher:
	dispatcher = Dispatcher()
	for i in range(static_routes):
		handler = Handler(noop, methods=[("GET", f"/static/{i}")])
		dispatcher.register(handler)
	for i in range(param_routes):
		handler = Handler(noop, methods=[("GET", f"/users/{i}/{{id:int}}/{{slug:name}}")])
		dispatcher.register(handler)
	dispatcher.prepare()
	return dispatcher


def bench_match(
	dispatcher: Dispatcher,
	paths: list[str],
	iterations: int,
	warmup: int,
) -> tuple[int, int]:
	n = len(paths)
	hits = 0
	for i in range(warmup):
		dispatcher.match("GET", paths[i % n])
	start = perf_counter_ns()
	for i in range(iterations):
		route, _ = dispatcher.match("GET", paths[i % n])
		if route is not None:
			hits += 1
	elapsed = perf_counter_ns() - start
	return elapsed, hits


def print_result(name: str, iterations: int, elapsed_ns: int, hits: int) -> None:
	ns_op = elapsed_ns / iterations
	ops_s = iterations * 1_000_000_000 / elapsed_ns if elapsed_ns else 0.0
	print(
		f"{name:12} ops={iterations:9d} time={elapsed_ns / 1_000_000:10.3f}ms "
		f"ns/op={ns_op:10.1f} ops/s={ops_s:12.1f} hits={hits:9d}"
	)


def main() -> None:
	parser = argparse.ArgumentParser(description="Core routing benchmark")
	parser.add_argument("--static-routes", type=int, default=500)
	parser.add_argument("--param-routes", type=int, default=500)
	parser.add_argument("--iterations", type=int, default=200_000)
	parser.add_argument("--warmup", type=int, default=20_000)
	parser.add_argument("--sample-size", type=int, default=512)
	args = parser.parse_args()

	dispatcher = build_dispatcher(args.static_routes, args.param_routes)

	static_hits = [f"/static/{i % args.static_routes}" for i in range(args.sample_size)]
	param_hits = [
		f"/users/{i % args.param_routes}/{(i * 7) % 10_000}/post-{i}"
		for i in range(args.sample_size)
	]
	misses = [f"/missing/{i}/path" for i in range(args.sample_size)]
	mixed = list(static_hits) + list(param_hits) + list(misses)
	random.Random(42).shuffle(mixed)

	print(
		"benchmark-routing "
		f"static_routes={args.static_routes} "
		f"param_routes={args.param_routes} "
		f"iterations={args.iterations} warmup={args.warmup}"
	)

	elapsed, hits = bench_match(dispatcher, static_hits, args.iterations, args.warmup)
	print_result("static-hit", args.iterations, elapsed, hits)

	elapsed, hits = bench_match(dispatcher, param_hits, args.iterations, args.warmup)
	print_result("param-hit", args.iterations, elapsed, hits)

	elapsed, hits = bench_match(dispatcher, misses, args.iterations, args.warmup)
	print_result("miss", args.iterations, elapsed, hits)

	elapsed, hits = bench_match(dispatcher, mixed, args.iterations, args.warmup)
	print_result("mixed", args.iterations, elapsed, hits)


if __name__ == "__main__":
	main()


# EOF
