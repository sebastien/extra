from typing import (
	Coroutine,
	Callable,
	Optional,
	Any,
	Iterable,
	Iterator,
	Pattern,
	Type,
	NamedTuple,
	ClassVar,
	TypeVar,
	Union,
	cast,
)
from .decorators import Transform, Extra, Expose
from .http.model import HTTPRequest, HTTPRequestError, HTTPResponse
from .utils.logging import info, warning
from inspect import iscoroutine, iscoroutinefunction

# TODO: Support re2, orjson
import re

# For Python 3.8 compatibility
Self = TypeVar("Self")
DispatcherT = TypeVar("DispatcherT", bound="Dispatcher")
T = TypeVar("T")


async def awaited(value: Any) -> Any:
	if iscoroutine(value):
		return await value
	else:
		return value


# -----------------------------------------------------------------------------
#
# ROUTE
#
# -----------------------------------------------------------------------------
#
# Routes represent collections/sets of paths that can be matched. Typically
# routes are made of chunks separated by a `/`.


class RoutePattern(NamedTuple):
	"""Used in a parameter chunk to extract/match from the give path."""

	expr: str
	extractor: Union[Type[Any], Callable[[str], Any]]


class TextChunk(NamedTuple):
	"""A raw text chunk"""

	text: str


class ParameterChunk(NamedTuple):
	"""A parameterizable chunk, where the chunk must match the given pattern."""

	name: str
	pattern: RoutePattern


TChunk = Union[TextChunk, ParameterChunk]


class Route:
	"""Parses a route where template expressions are like `{name}` or
	`{name:type}`. Routes can have priorities and be assigned handlers,
	they are then registered in the dispatcher to match requests."""

	RE_PATTERN_NAME: ClassVar[Pattern[str]] = re.compile("^[A-Za-z]+$")

	RE_TEMPLATE: ClassVar[Pattern[str]] = re.compile(
		r"\{(?P<name>[\w][_\w\d]*)(:(?P<type>[^}]+))?\}"
	)
	RE_SPECIAL: ClassVar[Pattern[str]] = re.compile(r"/\+\*\-\:")

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
		"chunk": RoutePattern(r"[^/]+", str),
		"topics": RoutePattern(
			r"[A-Za-z0-9_\-\.]+(/[A-Za-z0-9_\-\.]+)*", lambda _: _.split("/")
		),
		"path": RoutePattern(r"[^:@]+", str),
		"segment": RoutePattern(r"[^/]+", str),
		"any": RoutePattern(r".*", str),
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
	def Parse(cls, expression: str, isStart: bool = True) -> list[TChunk]:
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
		self.handler: Union[Handler, None] = handler
		self._pattern: Union[str, None] = None
		self._regexp: Union[Pattern[str], None] = None

	@property
	def priority(self) -> int:
		"""Returns the priority of te route, defined by `handler.priority`
		or defaulting to 0."""
		return self.handler.priority if self.handler else 0

	@property
	def pattern(self) -> str:
		"""Lazily returns the regexp pattern (as a string) for the route."""
		if not self._pattern:
			pat = self.toRegExp()
			self._pattern = pat
			return pat
		else:
			return self._pattern

	@property
	def regexp(self) -> Pattern[str]:
		if not self._regexp:
			# NOTE: Not sure if it's a good thing to have the prefix/suffix
			# for an exact match.

			try:
				self._regexp = re.compile(f"^{self.toRegExp()}$")
			except Exception as e:
				raise ValueError(
					warning(
						f"Route syntax is malformed: {repr(self.toRegExp())}",
						code="BADROUTE",
					).message
				) from e
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

	def match(self, path: str) -> Union[dict[str, Union[str, int, bool, float]], None]:
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
		return f'(Route "{self.toRegExp()}" ({" ".join(_ for _ in self.params)}))'


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
	def Compile(
		routes: Iterable[str],
	) -> tuple[Pattern[str], list[str], dict[int, list[tuple[str, str, list[str]]]]]:
		"""Compiles the list of routes into a single regex that can match
		all of these routes, and extract the arguments. Returns the compiled
		regex, an ordered list of route marker group names, and a mapping
		of route indices to their expected parameters as
		(name, type, candidate_group_names) tuples."""
		# --
		# This first step is where a bit of magic happens. We suffix each route
		# with a regexp match group that has a unique name like R_0_{0…n}.
		# --
		# We wrap that in a prefix tree so that we get a tree of strings
		# based on their common prefix.
		route_list = list(routes)
		tree = Prefix.Make(
			[f"{r}(?P<R_0_{i}>$)" for i, r in enumerate(route_list)]
		)
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
				p_type = (pat.group("type") or p_name).lower()
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
		compiled = re.compile("".join(chunks))
		# Build per-route expected params from the original templates,
		# with pre-resolved candidate group names from the compiled regex.
		markers: list[str] = [f"R_0_{i}" for i in range(len(route_list))]
		# Index all param group names by (name, type) prefix
		group_candidates: dict[str, list[str]] = {}
		for gname in compiled.groupindex:
			if not gname.startswith("R_"):
				key = "_".join(gname.split("_", 2)[:2])
				group_candidates.setdefault(key, []).append(gname)
		route_params: dict[int, list[tuple[str, str, list[str]]]] = {}
		for idx, route_text in enumerate(route_list):
			params: list[tuple[str, str, list[str]]] = []
			for pat in Route.RE_TEMPLATE.finditer(route_text):
				p_name = pat.group("name")
				p_type = (pat.group("type") or p_name).lower()
				key = f"{p_name}_{p_type}"
				params.append((p_name, p_type, group_candidates.get(key, [])))
			route_params[idx] = params
		return compiled, markers, route_params

	def __init__(self, *routes: str):
		self.paths = routes
		self.regexp: Pattern[str]
		self._markers: list[str]
		self._params: dict[int, list[tuple[str, str, list[str]]]]
		self.regexp, self._markers, self._params = Routes.Compile(routes)
		# Pre-compute marker group numeric indices for fast scanning
		# via match.regs (C-level tuple access).
		self._marker_info: tuple[tuple[int, int], ...] = tuple(
			(self.regexp.groupindex[mn], idx)
			for idx, mn in enumerate(self._markers)
		)
		# Pre-compute param group numeric indices per route for fast
		# extraction via match.group(int) instead of match.group(str).
		self._param_info: dict[int, tuple[tuple[str, str, tuple[int, ...]], ...]] = {}
		for ridx, param_list in self._params.items():
			self._param_info[ridx] = tuple(
				(
					p_name,
					p_type,
					tuple(self.regexp.groupindex[gn] for gn in candidates),
				)
				for p_name, p_type, candidates in param_list
			)

	def match(self, path: str) -> Union[tuple[int, dict[str, Any]], None]:
		if not (match := self.regexp.match(path)):
			return None
		else:
			# Find the route marker using match.regs for fast C-level access.
			regs = match.regs
			route: int = next(
				(ri for gi, ri in self._marker_info if regs[gi][0] >= 0), -1
			)
			if route < 0:
				return None
			# Extract only the matched route's params using numeric indices.
			params: dict[str, Any] = {}
			for p_name, p_type, candidates in self._param_info.get(route, ()):
				for gidx in candidates:
					value = match.group(gidx)
					if value is not None:
						params[p_name] = Route.PATTERNS[p_type].extractor(value)
						break
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
	def Make(self, values: Iterable[str]) -> "Prefix":
		root = Prefix()
		for _ in values:
			root.register(_)
		root.simplify()
		return root

	def __init__(
		self, value: Union[str, None] = None, parent: Optional["Prefix"] = None
	) -> None:
		self.value: Union[str, None] = value
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

	def register(self, text: str) -> None:
		"""Registers the given `text` in this prefix tree."""
		c: str = text[0] if text else ""
		rest: str = text[1:] if len(text) > 1 else ""
		if c:
			if c not in self.children:
				self.children[c] = Prefix(c, self)
			if rest:
				self.children[c].register(rest)

	def iterLines(self, level: int = 0) -> Iterable[str]:
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

	def __str__(self) -> str:
		return "\n".join(self.iterLines())

	def __repr__(self) -> str:
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
	def Has(cls, value: Any) -> bool:
		return hasattr(value, Extra.ON)

	@classmethod
	def Attr(
		cls,
		value: Any,
		key: str,
		extra: Union[dict[str, Any], None] = None,
		*,
		merge: bool = False,
	) -> Any:
		extra_value = extra[key] if extra and key in extra else None
		sid = id(value)
		exists: bool = False
		# This is to accommodate with
		if sid in Extra.Annotations:
			v: Any = Extra.Annotations[sid].get(key)
			exists = True
		elif hasattr(value, key):
			v = getattr(value, key)
			exists = True
		else:
			v = None
		if exists:
			# If we have a matching extra value, and we have that to
			# merge, then we merge it.
			if extra_value and merge:
				if type(extra_value) is type(v):
					if isinstance(v, dict):
						merged = dict()
						merged.update(extra_value)
						merged.update(v)
						v = merged
					elif isinstance(v, list):
						v = extra_value + v
					else:
						# We don't change anything
						pass
			return v
		else:
			return extra_value

	# FIXME: Handlers should compose transforms and predicate, right now it's
	# passed as attributes, but it should not really be a stack of transforms.
	@classmethod
	def Get(
		cls, value: Any, extra: Union[dict[str, Any], None] = None
	) -> Union[Any, None]:
		return (
			Handler(
				functor=value,
				methods=cls.Attr(value, Extra.ON),
				expose=cast(Expose, cls.Attr(value, Extra.EXPOSE)),
				priority=cls.Attr(value, Extra.ON_PRIORITY, extra),
				contentType=cls.Attr(value, Extra.EXPOSE_CONTENT_TYPE, extra),
				pre=cls.Attr(value, Extra.PRE, extra, merge=True),
				post=cls.Attr(value, Extra.POST, extra, merge=True),
			)
			if cls.Has(value)
			else None
		)

	def __init__(
		self,
		# TODO: Refine type
		functor: Callable[..., Any],
		methods: list[tuple[str, str]],
		priority: int = 0,
		expose: Union[Expose, None] = None,
		contentType: Union[str, None] = None,
		pre: Union[list[Transform], None] = None,
		post: Union[list[Transform], None] = None,
	) -> None:
		self.functor = functor
		# This extracts and normalizes the methods
		# NOTE: This may have been done at the decoartor level
		self.methods: dict[str, list[str]] = {}
		for method, path in methods:
			self.methods.setdefault(method, []).append(path)

		self.priority = priority
		self.expose = expose
		self.contentType = contentType
		self.pre: Union[list[Transform], None] = pre
		self.post: Union[list[Transform], None] = post
		self.isAsync: bool = iscoroutinefunction(functor)

	# TODO: This is maybe more than routing, not sure if this really belongs here
	# NOTE: For now we only do HTTP Requests, we'll see if we can generalise.
	def __call__(
		self, request: HTTPRequest, params: dict[str, Any]
	) -> Union[HTTPResponse, Coroutine[Any, HTTPResponse, Any]]:
		"""Dispatches to the sync or async path depending on the handler type.
		Returns an HTTPResponse directly for sync handlers, or a coroutine
		for async handlers -- avoiding coroutine creation overhead for sync."""
		if self.isAsync:
			return self._callAsync(request, params)
		else:
			return self._callSync(request, params)

	def _callSync(
		self, request: HTTPRequest, params: dict[str, Any]
	) -> HTTPResponse:
		"""Fast path for synchronous handlers -- no coroutine overhead."""
		if self.pre:
			for i, t in enumerate(self.pre):
				try:
					res = t.transform(request, params)
				except HTTPRequestError as error:
					return request.respondError(str(error))
				except Exception as e:
					raise e from e
				if isinstance(res, HTTPResponse):
					return res
				elif isinstance(res, HTTPRequestError):
					return request.respond(
						content=res.payload if res.payload else res.message,
						status=res.status or 500,
						contentType=res.contentType or "text/plain",
					)
				elif res is False:
					return request.fail(f"Precondition {1} failed")
		try:
			if self.expose:
				value: Any = self.functor(**params)
				content_type: str = (
					self.contentType or self.expose.contentType or "application/json"
				)
				response: HTTPResponse = (
					request.respond(value, contentType=content_type)
					if self.expose.raw
					else request.returns(value, contentType=content_type)
				)
			else:
				response = self.functor(request, **params)
		except HTTPRequestError as error:
			response = request.respond(
				content=error.payload if error.payload else error.message,
				status=error.status or 500,
				contentType=error.contentType or "text/plain",
			)
		if self.post:
			for t in self.post:
				t.transform(request, response, *t.args, **t.kwargs)
		return response

	async def _callAsync(
		self, request: HTTPRequest, params: dict[str, Any]
	) -> Union[HTTPResponse, Coroutine[Any, HTTPResponse, Any]]:
		if self.pre:
			for i, t in enumerate(self.pre):
				try:
					res = t.transform(request, params)
				except HTTPRequestError as error:
					return request.respondError(str(error))
				except Exception as e:
					raise e from e
				if isinstance(res, HTTPResponse):
					return res
				elif isinstance(res, HTTPRequestError):
					return request.respond(
						content=res.payload if res.payload else res.message,
						status=res.status or 500,
						contentType=res.contentType or "text/plain",
					)
				elif res is False:
					return request.fail(f"Precondition {1} failed")
		try:
			if self.expose:
				# NOTE: This pattern is hard to optimise, maybe we could do something
				# better, like code-generated dispatcher.
				value: Any = await awaited(self.functor(**params))
				content_type: str = (
					self.contentType or self.expose.contentType or "application/json"
				)
				# TODO: Handle compression
				response = (
					request.respond(value, contentType=content_type)
					if self.expose.raw
					else request.returns(value, contentType=content_type)
				)
			# TODO: Maybe we should handle the exception here and return an internal server error
			else:
				response = await awaited(self.functor(request, **params))
		except HTTPRequestError as error:
			# The `respond` method will take care of handling the different
			# types of responses there.
			# TODO
			response = request.respond(
				content=error.payload if error.payload else error.message,
				status=error.status or 500,
				contentType=error.contentType or "text/plain",
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

	def __repr__(self) -> str:
		methods = " ".join(
			f"({k} {' '.join(repr(_) for _ in v)})" for k, v in self.methods.items()
		)
		attrs = []
		if self.expose:
			attrs.append(":expose")
		if self.pre:
			attrs.append(f":pre({len(self.pre)})")
		if self.post:
			attrs.append(f":post({len(self.post)})")
		return (
			f"(Handler {self.priority} ({methods}) '{self.functor}' {' '.join(attrs)})"
		)


# -----------------------------------------------------------------------------
#
# DISPATCHER
#
# -----------------------------------------------------------------------------


class Dispatcher:
	"""A dispatcher registers handlers that respond to HTTP methods
	on a given path/URI. Uses a compiled prefix-tree regex for O(1)
	route matching and a dict fast-path for static routes."""

	def __init__(self) -> None:
		self.routes: dict[str, list[Route]] = {}
		# Static routes indexed by path for O(1) dict lookup
		self._static: dict[str, dict[str, Route]] = {}
		# Compiled single-regex matcher per method
		self._compiled: dict[str, Routes] = {}
		# Ordered route list per method, indices match the compiled regex
		self._indexed: dict[str, list[Route]] = {}
		self.isPrepared: bool = True

	def register(
		self, handler: Handler, prefix: Union[str, None] = None
	) -> "Dispatcher":
		"""Registers the handlers and their routes, adding the prefix if given."""
		for method, paths in handler.methods.items():
			for path in paths:
				path = f"{prefix}{path}" if prefix else path
				path = f"/{path}" if not path.startswith("/") else path
				route: Route = Route(path, handler)
				info("Registered route", Method=method, Path=path)
				self.routes.setdefault(method, []).append(route)
				self.isPrepared = False
		return self

	def prepare(self: DispatcherT) -> DispatcherT:
		"""Prepares the dispatcher by compiling routes into optimised
		matching structures: a dict for static routes and a single
		compiled regex (via prefix tree) for dynamic routes."""
		res: dict[str, list[Route]] = {}
		static: dict[str, dict[str, Route]] = {}
		indexed: dict[str, list[Route]] = {}
		compiled: dict[str, Routes] = {}
		for method, routes in self.routes.items():
			# Sort by descending priority so the first alternation match
			# in the compiled regex corresponds to the highest priority.
			sorted_routes = sorted(routes, key=lambda _: (-_.priority, _.pattern))
			res[method] = sorted_routes
			# Separate static (no params) from dynamic routes
			method_static: dict[str, Route] = {}
			dynamic_routes: list[Route] = []
			for route in sorted_routes:
				if not route.params:
					# Only keep the first (highest priority) static route
					if route.text not in method_static:
						method_static[route.text] = route
				else:
					dynamic_routes.append(route)
			static[method] = method_static
			indexed[method] = dynamic_routes
			if dynamic_routes:
				compiled[method] = Routes(*(r.text for r in dynamic_routes))
		self.routes = res
		self._static = static
		self._indexed = indexed
		self._compiled = compiled
		self.isPrepared = True
		return self

	def match(
		self, method: str, path: str
	) -> tuple[
		Union[Route, None], Union[bool, dict[str, Union[str, int, float, bool]], None]
	]:
		"""Matches a given `method` and `path` with the registered route, returning
		the matching route and the match information."""
		if not self.isPrepared:
			self.prepare()
		if method not in self.routes:
			return (None, False)
		static_route: Union[Route, None] = None
		# Fast path: O(1) dict lookup for static routes
		static = self._static.get(method)
		if static:
			static_route = static.get(path)
		# Compiled regex: single match for all dynamic routes
		comp = self._compiled.get(method)
		if comp:
			result = comp.match(path)
			if result is not None:
				route_index, params = result
				dynamic_route = self._indexed[method][route_index]
				if static_route is None:
					return (dynamic_route, params)
				# Keep old dispatcher semantics: pick highest priority,
				# and favour static on ties.
				if dynamic_route.priority > static_route.priority:
					return (dynamic_route, params)
				return (static_route, {})
		if static_route is not None:
			return (static_route, {})
		return (None, None)


# EOF
