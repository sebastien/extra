from extra.routing import Route

ROUTES = """\
post
post/
post/{id}
post/{id:name}
post/{id:segment}/path
""".split(
    "\n"
)

for route in ROUTES:
    print(f"=== TEST route='{route}'")
    print("... parsed", Route.Parse(route))
    print("... chunks", Route(route).toRegExpChunks())
    print("... regexp", Route(route).toRegExp())

# EOF
