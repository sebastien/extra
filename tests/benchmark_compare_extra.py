#!/usr/bin/env python3
import asyncio
import os
import sys
from pathlib import Path
from time import perf_counter_ns


ROOT = Path(__file__).resolve().parent.parent
SRC_PY = ROOT / "src" / "py"
if str(SRC_PY) not in sys.path:
	sys.path.insert(0, str(SRC_PY))

import extra.routing as routing  # noqa: E402
from extra.decorators import on  # noqa: E402
from extra.http.model import HTTPBodyBlob, HTTPHeaders, HTTPRequest, HTTPResponse  # noqa: E402
from extra.model import Service, mount  # noqa: E402
from benchmark_compare_common import (
	bench_server,
	benchmark_loop,
	build_routing_scenarios,
	print_result,
)  # noqa: E402


BACKEND_NAME = "extra"
routing.info = lambda *a, **k: None


def run_routing(args) -> dict[str, float]:
	from extra.routing import Dispatcher, Handler

	dispatcher = Dispatcher()
	for i in range(args.static_routes):
		handler = Handler(lambda req, **kw: None, methods=[("GET", f"/static/{i}")])
		dispatcher.register(handler)
	for i in range(args.param_routes):
		handler = Handler(
			lambda req, **kw: None, methods=[("GET", f"/users/{i}/{{id:int}}")]
		)
		dispatcher.register(handler)
	dispatcher.prepare()

	scenarios = build_routing_scenarios(
		args.static_routes, args.param_routes, args.sample_size
	)
	results: dict[str, float] = {}
	for name, paths in scenarios.items():
		elapsed = benchmark_loop(
			lambda p: dispatcher.match("GET", p), paths, args.iterations, args.warmup
		)
		results[name] = print_result(f"extra/{name}", args.iterations, elapsed)
	return results


class BenchExtraAPI(Service):
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


def _make_request(path: str) -> HTTPRequest:
	return HTTPRequest(
		method="GET",
		path=path,
		query=None,
		headers=HTTPHeaders(
			{"Host": "bench.local", "Connection": "keep-alive"},
			contentType=None,
			contentLength=0,
		),
		body=HTTPBodyBlob(b"", 0),
	)


async def _bench_reqres(
	app, requests: list[HTTPRequest], iterations: int, warmup: int
) -> int:
	n = len(requests)
	for i in range(warmup):
		res = app.process(requests[i % n])
		if not isinstance(res, HTTPResponse):
			res = await res
		res.head()
	start = perf_counter_ns()
	for i in range(iterations):
		res = app.process(requests[i % n])
		if not isinstance(res, HTTPResponse):
			res = await res
		res.head()
	return perf_counter_ns() - start


def run_reqres(args) -> dict[str, float]:
	from benchmark_compare_common import build_reqres_scenarios

	scenarios = build_reqres_scenarios(args.sample_size)
	app = mount(BenchExtraAPI())
	app.dispatcher.prepare()

	results: dict[str, float] = {}
	for name, paths in scenarios.items():
		reqs = [_make_request(p) for p in paths]
		elapsed = asyncio.run(_bench_reqres(app, reqs, args.iterations, args.warmup))
		results[name] = print_result(f"extra/{name}", args.iterations, elapsed)
	return results


def run_server(args, modes: tuple[str, ...]) -> dict[str, float | None] | None:
	tests = ROOT / "tests"
	env = dict(os.environ)
	env["PYTHONPATH"] = f"{SRC_PY}:{env.get('PYTHONPATH', '')}"
	env["HTTP_PORT"] = str(args.port)
	cmd = [sys.executable, str(tests / "benchmark-extra-aio.py")]
	return bench_server(
		BACKEND_NAME,
		cmd,
		env,
		"127.0.0.1",
		args.port,
		args.server_requests,
		args.server_concurrency,
		modes,
	)


# EOF
