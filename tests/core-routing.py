from extra.routing import Route
import re

ROUTES = {
    "post": (["post"], ["", "/post", "post/", "/post", "poster"]),
    "post/": (["post/"], ["", "/post/", "/post", "poster/"]),
    "post/{id}": (["post/a", "post/ab"], ["", "post/", "/post", "post/a/"]),
    # "post/{id:name}": (["post"], ["", "post/", "/post", "poster"]),
    # "post/{id:segment}/path": (["post"], ["", "post/", "/post", "poster"]),
}

failed: int = 0
for route in ROUTES:
    ok, no_ok = ROUTES[route]
    print(f"=== TEST route='{route}'")
    print("... parsed", Route.Parse(route))
    print("... chunks", Route(route).toRegExpChunks())
    print("... regexp", Route(route).toRegExp())
    r = Route(route)
    for t in ok:
        if r.match(t) is not None:
            print(f".-. OK!  '{t}' matched'")
        else:
            print(
                f".!. FAIL '{t}' should have been matched by '{route}' with '{r.toRegExp()}'"
            )
            failed += 1
    for t in no_ok:
        if not r.match(t):
            print(f".-. OK!  '{t}' did not match as expected")
        else:
            print(
                f".!. FAIL '{t}' should NOT have been matched by '{route}' with '{r.toRegExp()}'"
            )
            failed += 1
if failed:
    print("FAIL {failed} tests failed")
    print("ERR")
else:
    print("OK! All tests passed")
    print("EOK")


# EOF
