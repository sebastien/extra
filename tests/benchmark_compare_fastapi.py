#!/usr/bin/env python3
import asyncio
import os
import sys
from pathlib import Path
from time import perf_counter_ns

from benchmark_compare_common import (
	bench_server,
	benchmark_loop,
	build_routing_scenarios,
	print_result,
)


ROOT = Path(__file__).resolve().parent.parent
SRC_PY = ROOT / "src" / "py"

BACKEND_NAME = "fastapi"

try:
	from fastapi import FastAPI
	from fastapi.responses import PlainTextResponse as FAPlainTextResponse
	from starlette.responses import JSONResponse as SJSONResponse
	from starlette.responses import PlainTextResponse as SPlainTextResponse
	from starlette.routing import (
		Match,
		Route as StarletteRoute,
		Router as StarletteRouter,
	)

	AVAILABLE = True
except ImportError:
	AVAILABLE = False


def ensure_available() -> None:
	if AVAILABLE:
		return
	raise RuntimeError(
		"fastapi/starlette not installed. Install with: python -m pip install fastapi uvicorn"
	)


def run_routing(args) -> dict[str, float]:
	ensure_available()
	routes: list[StarletteRoute] = []

	async def noop(request):  # type: ignore
		pass

	for i in range(args.static_routes):
		routes.append(StarletteRoute(f"/static/{i}", noop, methods=["GET"]))
	for i in range(args.param_routes):
		routes.append(StarletteRoute(f"/users/{i}/{{id:int}}", noop, methods=["GET"]))

	def match(scope: dict) -> bool:
		for route in routes:
			m, _ = route.matches(scope)
			if m == Match.FULL:
				return True
		return False

	def make_scope(path: str) -> dict:
		return {
			"type": "http",
			"method": "GET",
			"path": path,
			"root_path": "",
			"path_params": {},
		}

	scenarios = build_routing_scenarios(
		args.static_routes, args.param_routes, args.sample_size
	)
	results: dict[str, float] = {}
	for name, paths in scenarios.items():
		scopes = [make_scope(p) for p in paths]
		elapsed = benchmark_loop(match, scopes, args.iterations, args.warmup)
		results[name] = print_result(f"starlette/{name}", args.iterations, elapsed)
	return results


def make_starlette_app() -> "StarletteRouter":
	ensure_available()

	async def plain(request):  # type: ignore
		return SPlainTextResponse("hello")

	async def json_ep(request):  # type: ignore
		return SJSONResponse({"ok": True, "value": 42})

	async def user_ep(request):  # type: ignore
		uid = request.path_params["id"]
		return SJSONResponse({"id": uid, "name": f"u{uid}"})

	async def async_user_ep(request):  # type: ignore
		uid = request.path_params["id"]
		return SJSONResponse({"id": uid, "async": True})

	return StarletteRouter(
		routes=[
			StarletteRoute("/plain", plain, methods=["GET"]),
			StarletteRoute("/json", json_ep, methods=["GET"]),
			StarletteRoute("/users/{id:int}", user_ep, methods=["GET"]),
			StarletteRoute("/async/{id:int}", async_user_ep, methods=["GET"]),
		]
	)


def make_fastapi_app() -> "FastAPI":
	ensure_available()
	app = FastAPI()

	@app.get("/plain", response_class=FAPlainTextResponse)
	def plain():
		return "hello"

	@app.get("/json")
	def json_ep():
		return {"ok": True, "value": 42}

	@app.get("/users/{id}")
	def user_ep(id: int):
		return {"id": id, "name": f"u{id}"}

	@app.get("/async/{id}")
	async def async_user_ep(id: int):
		return {"id": id, "async": True}

	return app


def make_asgi_scope(path: str, app) -> dict:  # type: ignore[type-arg]
	return {
		"type": "http",
		"method": "GET",
		"path": path,
		"root_path": "",
		"query_string": b"",
		"headers": [(b"host", b"bench.local"), (b"connection", b"keep-alive")],
		"app": app,
	}


async def _bench_asgi(app, scopes: list[dict], iterations: int, warmup: int) -> int:
	n = len(scopes)

	async def receive():
		return {"type": "http.request", "body": b""}

	responses: list[dict] = []

	async def send(message: dict) -> None:
		responses.append(message)

	for i in range(warmup):
		responses.clear()
		await app(scopes[i % n], receive, send)
	start = perf_counter_ns()
	for i in range(iterations):
		responses.clear()
		await app(scopes[i % n], receive, send)
	return perf_counter_ns() - start


def run_reqres(args) -> tuple[dict[str, float], dict[str, float]]:
	from benchmark_compare_common import build_reqres_scenarios

	ensure_available()
	scenarios = build_reqres_scenarios(args.sample_size)

	starlette = make_starlette_app()
	starlette_results: dict[str, float] = {}
	for name, paths in scenarios.items():
		scopes = [make_asgi_scope(p, starlette) for p in paths]
		elapsed = asyncio.run(
			_bench_asgi(starlette, scopes, args.iterations, args.warmup)
		)
		starlette_results[name] = print_result(
			f"starlette/{name}", args.iterations, elapsed
		)

	fastapi = make_fastapi_app()
	fastapi_results: dict[str, float] = {}
	for name, paths in scenarios.items():
		scopes = [make_asgi_scope(p, fastapi) for p in paths]
		elapsed = asyncio.run(
			_bench_asgi(fastapi, scopes, args.iterations, args.warmup)
		)
		fastapi_results[name] = print_result(
			f"fastapi/{name}", args.iterations, elapsed
		)

	return starlette_results, fastapi_results


def run_server(args, modes: tuple[str, ...]) -> dict[str, float | None] | None:
	cmd = [
		sys.executable,
		"-m",
		"uvicorn",
		"--host",
		"127.0.0.1",
		"--port",
		str(args.port),
		"--log-level",
		"warning",
		"benchmark_fastapi:app",
	]
	tests = ROOT / "tests"
	env = dict(os.environ)
	env["PYTHONPATH"] = f"{tests}:{SRC_PY}:{env.get('PYTHONPATH', '')}"
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
