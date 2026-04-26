from typing import Any

from extra.routing import Dispatcher, Handler


def noop(request, **params):
	return None


failed: int = 0


def check(label: str, ok: bool, detail: str) -> None:
	global failed
	if ok:
		print(f".-. OK   {label}")
	else:
		print(f".!. FAIL {label}: {detail}")
		failed += 1


def expect_match(
	dispatcher: Dispatcher,
	label: str,
	method: str,
	path: str,
	expected_route: str | None,
	expected_params: dict[str, Any] | None,
) -> None:
	route, params = dispatcher.match(method, path)
	if expected_route is None:
		check(label, route is None, f"expected no match, got route={route!r}")
		return
	if route is None:
		check(label, False, "expected a route, got None")
		return
	check(
		f"{label} route",
		route.text == expected_route,
		f"expected route={expected_route!r}, got route={route.text!r}",
	)
	check(
		f"{label} params",
		params == expected_params,
		f"expected params={expected_params!r}, got params={params!r}",
	)


print("=== AUTO-PREPARE REGRESSION")
d = Dispatcher()
d.register(Handler(noop, methods=[("GET", "/health")]))
d.register(Handler(noop, methods=[("GET", "/users/{id:int}")]))
expect_match(d, "auto-prepare static", "GET", "/health", "/health", {})
expect_match(
	d,
	"auto-prepare dynamic",
	"GET",
	"/users/42",
	"/users/{id:int}",
	{"id": 42},
)


print("=== PRIORITY REGRESSION (STATIC VS DYNAMIC)")
d = Dispatcher()
d.register(Handler(noop, methods=[("GET", "/post/query")], priority=0))
d.register(Handler(noop, methods=[("GET", "/post/{id}")], priority=10))
d.prepare()
expect_match(
	d,
	"higher-priority dynamic should win",
	"GET",
	"/post/query",
	"/post/{id}",
	{"id": "query"},
)


print("=== METHOD ISOLATION")
d = Dispatcher()
d.register(Handler(noop, methods=[("GET", "/articles/{id:int}")]))
d.prepare()
expect_match(
	d,
	"method GET hit",
	"GET",
	"/articles/7",
	"/articles/{id:int}",
	{"id": 7},
)
expect_match(d, "method POST miss", "POST", "/articles/7", None, None)


print("=== PREFIX NORMALIZATION")
d = Dispatcher()
d.register(Handler(noop, methods=[("GET", "/status")]), prefix="api")
d.register(Handler(noop, methods=[("GET", "/ping")]), prefix="/v1")
d.prepare()
expect_match(d, "prefix without slash", "GET", "/api/status", "/api/status", {})
expect_match(d, "prefix with slash", "GET", "/v1/ping", "/v1/ping", {})


print("=== PARAM EXTRACTION")
d = Dispatcher()
d.register(Handler(noop, methods=[("GET", "/n/{v:number}")]))
d.register(Handler(noop, methods=[("GET", "/p/{parts:topics}")]))
d.prepare()
expect_match(d, "number int", "GET", "/n/12", "/n/{v:number}", {"v": 12})
expect_match(d, "number float", "GET", "/n/12.5", "/n/{v:number}", {"v": 12.5})
expect_match(
	d,
	"topics list",
	"GET",
	"/p/a/b-c.d",
	"/p/{parts:topics}",
	{"parts": ["a", "b-c.d"]},
)


print("=== MISS SHAPES")
d = Dispatcher()
d.register(Handler(noop, methods=[("GET", "/ok")]))
d.prepare()
route, params = d.match("DELETE", "/ok")
check("missing method route", route is None, f"expected route None, got {route!r}")
check(
	"missing method params",
	params is False,
	f"expected params False for missing method, got {params!r}",
)
route, params = d.match("GET", "/missing")
check("missing path route", route is None, f"expected route None, got {route!r}")
check(
	"missing path params",
	params is None,
	f"expected params None for missing path, got {params!r}",
)


if failed:
	print(f"FAIL {failed} checks failed")
	print("ERR")
else:
	print("OK! All checks passed")
	print("EOK")


# EOF
