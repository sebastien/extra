#!/usr/bin/env python3
import argparse
import asyncio
import gc
import os
import random
import statistics
from time import perf_counter_ns

import extra.routing as routing
from extra.decorators import on
from extra.http.model import HTTPBodyBlob, HTTPHeaders, HTTPRequest, HTTPResponse
from extra.model import Service, mount


def _quiet_info(*args, **kwargs):
	return None


def pin_cpu() -> None:
	"""Pin to one core when possible to cut scheduler noise."""
	try:
		os.sched_setaffinity(0, {0})
	except (AttributeError, OSError, ValueError):
		pass


routing.info = _quiet_info


class BenchAPI(Service):
	@on(GET="/plain")
	def plain(self, request: HTTPRequest) -> HTTPResponse:
		return request.respondText("hello")

	@on(GET="/json")
	def asjson(self, request: HTTPRequest) -> HTTPResponse:
		return request.returns({"ok": True, "value": 42})

	@on(GET="/users/{id:int}")
	def user(self, request: HTTPRequest, id: int) -> HTTPResponse:
		return request.returns({"id": id, "name": f"u{id}"})

	@on(GET="/async/{id:int}")
	async def async_user(self, request: HTTPRequest, id: int) -> HTTPResponse:
		return request.returns({"id": id, "async": True})


def make_request(path: str) -> HTTPRequest:
	return HTTPRequest(
		method="GET",
		path=path,
		query=None,
		headers=HTTPHeaders(
			{
				"Host": "bench.local",
				"Connection": "keep-alive",
			},
			contentType=None,
			contentLength=0,
		),
		body=HTTPBodyBlob(b"", 0),
	)


def print_result(
	name: str,
	iterations: int,
	elapsed_ns: int,
	samples: list[int],
) -> None:
	nsOp = elapsed_ns / iterations
	opsS = iterations * 1_000_000_000 / elapsed_ns if elapsed_ns else 0.0
	spread = 0.0
	if samples and elapsed_ns:
		core = sorted(samples)[1:-1] if len(samples) >= 5 else samples
		lo = min(core) / iterations
		hi = max(core) / iterations
		spread = (hi - lo) / nsOp * 100.0 if nsOp else 0.0
	print(
		f"{name:12} ops={iterations:9d} time={elapsed_ns / 1_000_000:10.3f}ms "
		f"ns/op={nsOp:10.1f} ops/s={opsS:12.1f} spread={spread:4.1f}%"
	)


async def calibrate_iterations(
	app,
	requests: list[HTTPRequest],
	serialize_head: bool,
	target_ms: float,
	floor: int,
	ceiling: int,
) -> int:
	n = len(requests)
	probe = min(max(floor // 10, 1_000), ceiling)
	for i in range(probe):
		res = app.process(requests[i % n])
		res = res if isinstance(res, HTTPResponse) else await res
		if serialize_head:
			res.head()
	start = perf_counter_ns()
	for i in range(probe):
		res = app.process(requests[i % n])
		res = res if isinstance(res, HTTPResponse) else await res
		if serialize_head:
			res.head()
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


async def bench_async(
	app,
	requests: list[HTTPRequest],
	iterations: int,
	warmup: int,
	serialize_head: bool,
	rounds: int,
) -> tuple[int, list[int]]:
	"""Returns (stable elapsed ns, samples)."""
	n = len(requests)
	for i in range(warmup):
		res = app.process(requests[i % n])
		res = res if isinstance(res, HTTPResponse) else await res
		if serialize_head:
			res.head()
	samples: list[int] = []
	gc.collect()
	wasEnabled = gc.isenabled()
	gc.disable()
	try:
		for _ in range(rounds):
			start = perf_counter_ns()
			for i in range(iterations):
				res = app.process(requests[i % n])
				res = res if isinstance(res, HTTPResponse) else await res
				if serialize_head:
					res.head()
			samples.append(perf_counter_ns() - start)
	finally:
		if wasEnabled:
			gc.enable()
	return stable_elapsed(samples), samples


def main() -> None:
	parser = argparse.ArgumentParser(description="Core request/response benchmark")
	parser.add_argument(
		"--iterations",
		type=int,
		default=0,
		help="Fixed iterations per round (0 = auto-calibrate to --target-ms)",
	)
	parser.add_argument("--warmup", type=int, default=15_000)
	parser.add_argument("--sample-size", type=int, default=256)
	parser.add_argument("--no-head", action="store_true")
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
	parser.add_argument("--min-iterations", type=int, default=10_000)
	parser.add_argument("--max-iterations", type=int, default=1_000_000)
	args = parser.parse_args()
	pin_cpu()

	app = mount(BenchAPI())
	app.dispatcher.prepare()
	serializeHead = not args.no_head

	plainRequests = [make_request("/plain") for _ in range(args.sample_size)]
	jsonRequests = [make_request("/json") for _ in range(args.sample_size)]
	paramRequests = [
		make_request(f"/users/{(i * 17) % 10_000}") for i in range(args.sample_size)
	]
	asyncRequests = [
		make_request(f"/async/{(i * 11) % 10_000}") for i in range(args.sample_size)
	]
	mixedRequests = (
		list(plainRequests)
		+ list(jsonRequests)
		+ list(paramRequests)
		+ list(asyncRequests)
	)
	random.Random(7).shuffle(mixedRequests)

	print(
		"benchmark-reqres "
		f"warmup={args.warmup} serialize_head={serializeHead} "
		f"rounds={args.rounds} "
		f"target_ms={args.target_ms if args.iterations <= 0 else 'fixed'}"
	)

	async def run() -> None:
		for name, requests in (
			("plain-sync", plainRequests),
			("json-sync", jsonRequests),
			("param-sync", paramRequests),
			("async", asyncRequests),
			("mixed", mixedRequests),
		):
			iterations = args.iterations
			if iterations <= 0:
				iterations = await calibrate_iterations(
					app,
					requests,
					serializeHead,
					args.target_ms,
					args.min_iterations,
					args.max_iterations,
				)
			elapsed, samples = await bench_async(
				app,
				requests,
				iterations,
				args.warmup,
				serializeHead,
				args.rounds,
			)
			print_result(name, iterations, elapsed, samples)

	asyncio.run(run())


if __name__ == "__main__":
	main()


# EOF
