#!/usr/bin/env python3
import argparse
import asyncio
import random
from time import perf_counter_ns

import extra.routing as routing
from extra.decorators import on
from extra.http.model import HTTPBodyBlob, HTTPHeaders, HTTPRequest, HTTPResponse
from extra.model import Service, mount


def _quiet_info(*args, **kwargs):
	return None


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


def print_result(name: str, iterations: int, elapsed_ns: int) -> None:
	ns_op = elapsed_ns / iterations
	ops_s = iterations * 1_000_000_000 / elapsed_ns if elapsed_ns else 0.0
	print(
		f"{name:12} ops={iterations:9d} time={elapsed_ns / 1_000_000:10.3f}ms "
		f"ns/op={ns_op:10.1f} ops/s={ops_s:12.1f}"
	)


async def bench_async(
	app,
	requests: list[HTTPRequest],
	iterations: int,
	warmup: int,
	serialize_head: bool,
) -> int:
	n = len(requests)
	for i in range(warmup):
		res = app.process(requests[i % n])
		res = res if isinstance(res, HTTPResponse) else await res
		if serialize_head:
			res.head()
	start = perf_counter_ns()
	for i in range(iterations):
		res = app.process(requests[i % n])
		res = res if isinstance(res, HTTPResponse) else await res
		if serialize_head:
			res.head()
	elapsed = perf_counter_ns() - start
	return elapsed


def main() -> None:
	parser = argparse.ArgumentParser(description="Core request/response benchmark")
	parser.add_argument("--iterations", type=int, default=150_000)
	parser.add_argument("--warmup", type=int, default=15_000)
	parser.add_argument("--sample-size", type=int, default=256)
	parser.add_argument("--no-head", action="store_true")
	args = parser.parse_args()

	app = mount(BenchAPI())
	app.dispatcher.prepare()
	serialize_head = not args.no_head

	plain_requests = [make_request("/plain") for _ in range(args.sample_size)]
	json_requests = [make_request("/json") for _ in range(args.sample_size)]
	param_requests = [
		make_request(f"/users/{(i * 17) % 10_000}") for i in range(args.sample_size)
	]
	async_requests = [
		make_request(f"/async/{(i * 11) % 10_000}") for i in range(args.sample_size)
	]
	mixed_requests = (
		list(plain_requests)
		+ list(json_requests)
		+ list(param_requests)
		+ list(async_requests)
	)
	random.Random(7).shuffle(mixed_requests)

	print(
		"benchmark-reqres "
		f"iterations={args.iterations} warmup={args.warmup} "
		f"serialize_head={serialize_head}"
	)

	elapsed = asyncio.run(
		bench_async(
			app,
			plain_requests,
			args.iterations,
			args.warmup,
			serialize_head,
		)
	)
	print_result("plain-sync", args.iterations, elapsed)

	elapsed = asyncio.run(
		bench_async(
			app,
			json_requests,
			args.iterations,
			args.warmup,
			serialize_head,
		)
	)
	print_result("json-sync", args.iterations, elapsed)

	elapsed = asyncio.run(
		bench_async(
			app,
			param_requests,
			args.iterations,
			args.warmup,
			serialize_head,
		)
	)
	print_result("param-sync", args.iterations, elapsed)

	elapsed = asyncio.run(
		bench_async(
			app,
			async_requests,
			args.iterations,
			args.warmup,
			serialize_head,
		)
	)
	print_result("async", args.iterations, elapsed)

	elapsed = asyncio.run(
		bench_async(
			app,
			mixed_requests,
			args.iterations,
			args.warmup,
			serialize_head,
		)
	)
	print_result("mixed", args.iterations, elapsed)


if __name__ == "__main__":
	main()


# EOF
