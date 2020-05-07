from extra import Route

ROUTES = """\
post
post/
post/{id}
post/{id:name}
post/{id:segment}/path
""".split("\n")

for route in ROUTES:
	print (Route.Parse(route))

