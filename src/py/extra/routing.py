from typing import (
    Optional,
    Coroutine,
    Callable,
    Any,
    Iterable,
    Iterator,
    Pattern,
    Type,
    Union,
    NamedTuple,
    ClassVar,
    TypeVar,
)
from .protocols.http import HTTPRequest, HTTPResponse, HTTPRequestError
from .decorators import Transform, EXTRA
from .logging import logger
from inspect import iscoroutine

# TODO: Support re2, orjson
import re

logging = logger("extra.routing")

# -----------------------------------------------------------------------------
#
# ROUTE
#
# -----------------------------------------------------------------------------

T = TypeVar("T")


class RoutePattern(NamedTuple):
    expr: str
    extractor: Union[Type[Any], Callable[[str], Any]]


class TextChunk(NamedTuple):
    text: str


class ParameterChunk(NamedTuple):
    name: str
    pattern: RoutePattern


TChunk = Union[TextChunk, ParameterChunk]


class Route:
    """Parses a route where template expressions are like `{name}` or
    `{name:type}`. Routes can have priorities and be assigned handlers,
    they are then registered in the dispatcher to match requests."""

    RE_PATTERN_NAME: ClassVar[Pattern] = re.compile("^[A-Za-z]+$")

    RE_TEMPLATE: ClassVar[Pattern] = re.compile(
        r"\{(?P<name>[\w][_\w\d]*)(:(?P<type>[^}]+))?\}"
    )
    RE_SPECIAL: ClassVar[Pattern] = re.compile(r"/\+\*\-\:")

    PATTERNS: ClassVar[dict[str, RoutePattern]] = {
        "id": RoutePattern(r"[a-zA-Z0-9\-_]+", str),
        "word": RoutePattern(r"\w+", str),
        "name": RoutePattern(r"\w[\-\w]*", str),
        "alpha": RoutePattern(r"[a-zA-Z]+", str),
        "string": RoutePattern(r"[^/]+", str),
        "digits": RoutePattern(r"\d+", int),
        "number": RoutePattern(
            r"\-?\d*\.?\d+", lambda x: x.find(".") != -1 and float(x) or int(x)
        ),
        "int": RoutePattern(r"\-?\d+", int),
        "integer": RoutePattern(r"\-?\d+", int),
        "float": RoutePattern(r"\-?\d*.?\d+", float),
        "file": RoutePattern(r"\w+(.\w+)", str),
        "chunk": RoutePattern(r"[^/^.]+", str),
        "topics": RoutePattern(
            r"[A-Za-z0-9_-\.]+(/[A-Za-z0-9_-\.]+)*", lambda _: _.split("/")
        ),
        "path": RoutePattern(r"[^:@]+", str),
        "segment": RoutePattern(r"[^/]+", str),
        "any": RoutePattern(r".+", str),
        "rest": RoutePattern(r".+", str),
        "range": RoutePattern(r"\-?\d*\:\-?\d*", lambda x: x.split(":")),
        "lang": RoutePattern(r"((\w\w)/)?", lambda x: x[:-1]),
    }

    @classmethod
    def AddPattern(
        cls,
        type: str,
        regexp: str,
        parser: Union[Type[str], Callable[[str], Any]] = str,
    ) -> "RoutePattern":
        """Registers a new RoutePattern into `Route.PATTERNS`"""
        # We do a precompilation to make sure it's working
        try:
            re.compile(regexp)
        except Exception as e:
            raise ValueError(f"Regular expression '{regexp}' is malformed: {e}")
        res: RoutePattern = RoutePattern(regexp, parser)
        cls.PATTERNS[type.lower()] = res
        return res

    @classmethod
    def Parse(cls, expression: str, isStart=True) -> list[TChunk]:
        """Parses routes expressses as strings where patterns are denoted
        as `{name}` or `{name:pattern}`"""
        chunks: list[TChunk] = []
        offset: int = 0
        # We escape the special characters
        # escape = lambda _:cls.RE_SPECIAL.sub(lambda _:"\\" + _, _)
        for match in cls.RE_TEMPLATE.finditer(expression):
            chunks.append(TextChunk(expression[offset : match.start()]))
            name: str = match.group(1)
            pattern: str = (match.group(3) or name).lower()
            if pattern not in cls.PATTERNS:
                if cls.RE_PATTERN_NAME.match(pattern):
                    raise ValueError(
                        f"Route pattern '{pattern}' is not registered, pick one of: {', '.join(sorted(cls.PATTERNS.keys()))}"
                    )
                else:
                    # This creates a pattern in case the pattern is not a named
                    # pattern.
                    pat = RoutePattern(pattern, str)
            else:
                pat = cls.PATTERNS[pattern]
            chunks.append(ParameterChunk(name, pat))
            offset = match.end()
        chunks.append(TextChunk(expression[offset:]))
        return chunks

    def __init__(self, text: str, handler: Optional["Handler"] = None):
        self.text: str = text
        self.chunks: list[TChunk] = self.Parse(text)
        self.params: dict[str, ParameterChunk] = {
            _.name: _ for _ in self.chunks if isinstance(_, ParameterChunk)
        }
        self.handler: Optional[Handler] = handler
        self._pattern: Optional[str] = None
        self._regexp: Optional[Pattern] = None

    @property
    def priority(self) -> int:
        return self.handler.priority if self.handler else 0

    @property
    def pattern(self) -> str:
        if not self._pattern:
            pat = self.toRegExp()
            self._pattern = pat
            return pat
        else:
            return self._pattern

    @property
    def regexp(self) -> Pattern:
        if not self._regexp:
            # NOTE: Not sure if it's a good thing to have the prefix/suffix
            # for an exact match.
            self._regexp = re.compile(f"^{self.toRegExp()}$")
        return self._regexp

    def toRegExpChunks(self) -> list[str]:
        res: list[str] = []
        for chunk in self.chunks:
            if isinstance(chunk, TextChunk):
                res.append(chunk.text)
            elif isinstance(chunk, ParameterChunk):
                res.append(f"(?P<{chunk.name}>{chunk.pattern.expr})")
            else:
                raise ValueError(f"Unsupported chunk type: {chunk}")
        return res

    def toRegExp(self) -> str:
        return "".join(self.toRegExpChunks())

    def match(self, path: str) -> Optional[dict[str, Union[str, int, bool, float]]]:
        matches = self.regexp.match(path)
        return (
            {
                k: (
                    e(matches.group(k))
                    if (e := v.pattern.extractor)
                    else matches.group(k)
                )
                for k, v in self.params.items()
            }
            if matches
            else None
        )

    def __repr__(self) -> str:
        return f"(Route \"{self.toRegExp()}\" ({' '.join(_ for _ in self.params)}))"


# -----------------------------------------------------------------------------
#
# ROUTES
#
# -----------------------------------------------------------------------------

# --
# Routes are smarter, more efficient way to manage the routing mechanism
# than individual routes. Routes can compile a set of paths into a single
# regexp that can be matched. From the matching information, the
# route and its parameters can be extracted.


class Routes:
    """The routes can compile a set of path containing route template
    expressions into a single"""

    @staticmethod
    def Compile(routes: Iterable[str]) -> Pattern:
        """Compiles the list of routes into a single regex that can match
        all of these routes, and extract the arguments."""
        # --
        # This first step is where a bit of magic happens. We suffix each route
        # with a regexp match group that has a unique name like R_0_{0…n}.
        # --
        # We wrap that in a prefix tree so that we get a tree of strings
        # based on their common prefix.
        tree = Prefix.Make([f"{r}(?P<R_0_{i}>$)" for i, r in enumerate(routes)])
        j: int = 0
        chunks: list[str] = []
        # Now we iterate on the regular expression version of the prefix
        # tree, look for pattern templates and replace them.
        for chunk in tree.iterRegExpr():
            i: int = 0
            n: int = len(chunk)
            for pat in Route.RE_TEMPLATE.finditer(chunk):
                if pat.start() != i:
                    chunks.append(chunk[i : pat.start()])
                p_name = pat.group("name")
                p_type = pat.group("type") or p_name
                # Here again to avoid duplicate groups, we add a numeric
                # suffix to the group name, and also add the pattern type,
                # which we can use later to apply the extractor.
                chunks.append(
                    f"(?P<{p_name}_{p_type}_{j}>{Route.PATTERNS[p_type].expr})"
                )
                j += 1
                i = pat.end()
            if i < n:
                chunks.append(chunk[i:])
        return re.compile("".join(chunks))

    def __init__(self, *routes: str):
        self.paths = routes
        self.regexp: Pattern = Routes.Compile(routes)

    def match(self, path: str) -> Optional[tuple[int, dict[str, Any]]]:
        if not (match := self.regexp.match(path)):
            return None
        else:
            route: int = 0
            params: dict[str, Any] = {}
            for name, value in match.groupdict().items():
                if value is None:
                    continue
                else:
                    name, ptype, index = name.split("_", 2)
                    if name == "R":
                        route = int(index)
                    else:
                        params[name] = Route.PATTERNS[ptype].extractor(value)
            return (route, params)


# -----------------------------------------------------------------------------
#
# PREFIX
#
# -----------------------------------------------------------------------------


class Prefix:
    """A node in a prefix tree. Prefixes are used to find matches given a
    string."""

    @classmethod
    def Make(self, values: Iterable[str]):
        root = Prefix()
        for _ in values:
            root.register(_)
        root.simplify()
        return root

    def __init__(self, value: Optional[str] = None, parent: Optional["Prefix"] = None):
        self.value: Optional[str] = value
        self.parent = parent
        self.children: dict[str, Prefix] = {}

    def simplify(self) -> "Prefix":
        """Simplifies the prefix tree by joining together nodes that are similar"""
        children: dict[str, Prefix] = self.children
        # Any consecutive chain like A―B―C gets simplified to ABC
        while len(children) == 1:
            for key, prefix in children.items():
                self.value = key if not self.value else self.value + key
                children = prefix.children
                break
        # We recursively simplify the children
        self.children = dict((k, v.simplify()) for k, v in children.items())
        return self

    def register(self, text: str):
        """Registers the given `text` in this prefix tree."""
        c: str = text[0] if text else ""
        rest: str = text[1:] if len(text) > 1 else ""
        if c:
            if c not in self.children:
                self.children[c] = Prefix(c, self)
            if rest:
                self.children[c].register(rest)

    def iterLines(self, level=0) -> Iterable[str]:
        yield f"{self.value or '┐'}"
        last_i = len(self.children) - 1
        for i, child in enumerate(self.children.values()):
            for j, line in enumerate(child.iterLines(level + 1)):
                leader = ("└─ " if i == last_i else "├─ ") if j == 0 else "   "
                yield leader + line

    def toRegExpr(self) -> str:
        return "".join(_ for _ in self.iterRegExpr())

    def iterRegExpr(self) -> Iterator[str]:
        if self.value:
            yield self.value
        if self.children:
            for i, _ in enumerate(self.children):
                yield "(" if i == 0 else "|"
                yield from self.children[_].iterRegExpr()
            yield ")"

    def __str__(self):
        return "\n".join(self.iterLines())

    def __repr__(self):
        return f"'{self.value or '⦰'}'→({', '.join(repr(_) for _ in self.children.values())})"


# -----------------------------------------------------------------------------
#
# HANDLER
#
# -----------------------------------------------------------------------------


class Handler:
    """A handler wraps a function and maps it to paths for HTTP methods,
    along with a priority. The handler is used by the dispatchers to match
    a request."""

    @classmethod
    def Has(cls, value):
        return hasattr(value, EXTRA.ON)

    @classmethod
    def Attr(cls, value, key: str) -> Any:
        return getattr(value, key) if hasattr(value, key) else None

    # FIXME: Handlers should compose transforms and predicate, right now it's
    # passed as attributes, but it should not really be a stack of transforms.
    @classmethod
    def Get(cls, value):
        return (
            Handler(
                functor=value,
                methods=cls.Attr(value, EXTRA.ON),
                priority=cls.Attr(value, EXTRA.ON_PRIORITY),
                expose=cls.Attr(value, EXTRA.EXPOSE),
                contentType=cls.Attr(value, EXTRA.EXPOSE_CONTENT_TYPE),
                pre=cls.Attr(value, EXTRA.PRE),
                post=cls.Attr(value, EXTRA.POST),
            )
            if cls.Has(value)
            else None
        )

    def __init__(
        self,
        functor: Callable,
        methods: list[tuple[str, str]],
        priority: int = 0,
        expose: bool = False,
        contentType=None,
        pre: list[Transform] | None = None,
        post: list[Transform] | None = None,
    ):
        self.functor = functor
        # This extracts and normalizes the methods
        # NOTE: This may have been done at the decoartor level
        self.methods: dict[str, list[str]] = {}
        for method, path in methods:
            self.methods.setdefault(method, []).append(path)

        self.priority = priority
        self.expose = expose
        self.contentType = (
            bytes(contentType, "utf8") if isinstance(contentType, str) else contentType
        )
        self.pre: list[Transform] | None = pre
        self.post: list[Transform] | None = post

    # NOTE: For now we only do HTTP Requests, we'll see if we can generalise.
    def __call__(
        self, request: HTTPRequest, params: dict[str, Any]
    ) -> HTTPResponse | Coroutine[Any, HTTPResponse, Any]:
        if self.pre:
            # TODO
            pass
        try:
            if self.expose:
                # NOTE: This pattern is hard to optimise, maybe we could do something
                # better, like code-generated dispatcher.
                value: Any = self.functor(**params)
                response = request.returns(
                    value, self.contentType or b"application/json"
                )
            # TODO: Maybe we should handle the exception here and return an internal server error
            else:
                response = self.functor(request, **params)
        except HTTPRequestError as error:
            # The `respond` method will take care of handling the different
            # types of responses there.
            response = request.respond(
                value=error.payload or error.message,
                contentType=error.contentType or b"text/plain; chartset=UTF8",
                status=error.status or 400,
            )

        if self.post:
            if iscoroutine(response):

                async def postprocess(request, response, transforms):
                    r = await response
                    for _ in transforms:
                        _.transform(request, r, *_.args, **_.kwargs)
                    return r

                return postprocess(request, response, self.post)

            else:
                if self.post:
                    for t in self.post:
                        t.transform(request, response, *t.args, **t.kwargs)
        return response

    def __repr__(self):
        methods = " ".join(f'({k} "{v}")' for k, v in self.methods)
        return f"(Handler {self.priority} ({methods}) '{self.functor}' {' :expose' if self.expose else ''})"


# -----------------------------------------------------------------------------
#
# DISPATCHER
#
# -----------------------------------------------------------------------------


# TODO: The dispatcher should use the Routes instead
class Dispatcher:
    """A dispatcher registers handlers that respond to HTTP methods
    on a given path/URI."""

    def __init__(self) -> None:
        self.routes: dict[str, list[Route]] = {}
        self.isPrepared: bool = True

    def register(self, handler: Handler, prefix: Optional[str] = None) -> "Dispatcher":
        """Registers the handlers and their routes, adding the prefix if given."""
        for method, paths in handler.methods.items():
            for path in paths:
                path = f"{prefix}{path}" if prefix else path
                path = f"/{path}" if not path.startswith("/") else path
                route: Route = Route(path, handler)
                logging.info(
                    f"Registered route {','.join(handler.methods.keys())}: {path}"
                )
                self.routes.setdefault(method, []).append(route)
                self.isPrepared = False
        return self

    def prepare(self):
        """Prepares the dispatcher, which optimizes the prefix tree for faster matching."""
        res = {}
        for method, routes in self.routes.items():
            res[method] = sorted(routes, key=lambda _: _.pattern)
        self.routes = res
        self.isPrepared = True
        return self

    def match(
        self, method: str, path: str
    ) -> tuple[
        Optional[Route], Optional[Union[bool, dict[str, Union[str, int, float, bool]]]]
    ]:
        """Matches a given `method` and `path` with the registered route, returning
        the matching route and the match information."""
        if method not in self.routes:
            return (None, False)
        else:
            matched_match: Optional[dict[str, Union[str, bool, int, float]]] = None
            matched_route: Optional[Route] = None
            matched_priority: int = -1
            # TODO: Use Routes
            # NOTE: The problem here is that we're going through
            # *all* the registered routes for any URL. So the more routes,
            # the slower this is going to be.
            # ---
            # FIXME: This is a critical performance issue
            for route in self.routes[method]:
                if route.priority < matched_priority:
                    continue
                match: Optional[dict[str, Union[str, bool, int, float]]] = route.match(
                    path
                )
                # FIXME: Maybe use a debug stream here
                if match is None:
                    continue
                elif route.priority >= matched_priority:
                    matched_match = match
                    matched_route = route
                    matched_priority = route.priority
            return (
                (matched_route, matched_match)
                if matched_match is not None
                else (None, None)
            )


# EOF
