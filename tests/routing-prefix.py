from extra.routing import Prefix
import re

# --
# The prefix trees are what makes Extra's dispatching fast, as the prefix
# trees can do a match with just one query instead of many.

# --
# At the very core, a prefix tree will take a list of strings, and
# group them by common prefix. It's pretty straighforward.
prefix = Prefix.Make(
    (
        "post",
        "post/",
        "post/pouet",
        "post/something-like-that",
        "post/query",
        "posts/query",
    )
)

expected: str = """\
post
├─ /
   ├─ pouet
   ├─ something-like-that
   └─ query
└─ s/query"""
assert str(prefix.simplify()) == expected


# --
# Now, were things get interesting, is that when we can use them
# to match an HTTP path with a single regular expression, finding the matching
# route and extracting the parameters, all at the same time.
def route(i: int, route: str) -> str:
    return f"{route}(?P<R{i}>$)"


# We add a trailing '?' to our list of strings so that
# we get proper splits
prefix = Prefix.Make(
    (
        route(i, _)
        for i, _ in enumerate(
            [
                "users",
                "user/{id}",
                "user/{id}/posts",
                "posts",
                "posts/query",
                "post/{id}",
                "post/{id}/query",
            ]
        )
    )
)

print(prefix.simplify())
print(prefix.toRegExpr())
# TODO: We need to find a workaround to the duplicate ids
regexp = re.compile(prefix.toRegExpr().replace("{id}", r"(?P<id>\w+)"))
for path in [
    "users",
    "user/john",
    "user/john/posts",
    "posts",
    "posts/query",
    "posts/query",
    "post/hello",
    "post/hello/query",
]:
    if match := regexp.match(path):
        print(f"... OK '{path}' matched: {match.groupdict()}")
    else:
        print(f"... FAIL '{path}' did not match")
# EOF
