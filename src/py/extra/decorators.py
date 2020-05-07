import functools
from typing import List, Callable

EXTRA_ON                   = "_extra_on"
EXTRA_ON_PRIORITY          = "_extra_on_priority"
EXTRA_EXPOSE               = "_extra_expose"
EXTRA_EXPOSE_JSON          = "_extra_expose_json"
EXTRA_EXPOSE_RAW           = "_extra_expose_raw"
EXTRA_EXPOSE_COMPRESS      = "_extra_expose_compress"
EXTRA_EXPOSE_CONTENT_TYPE  = "_extra_expose_content_type"
EXTRA_WHEN                 = "_extra_when"
EXTRA_EXTRA = (
	EXTRA_ON                   ,
	EXTRA_ON_PRIORITY          ,
	EXTRA_EXPOSE               ,
	EXTRA_EXPOSE_JSON          ,
	EXTRA_EXPOSE_RAW           ,
	EXTRA_EXPOSE_COMPRESS      ,
	EXTRA_EXPOSE_CONTENT_TYPE  ,
	EXTRA_WHEN                 ,
)

def on( priority=0, **methods ):
	"""The @on decorator is one of the main important things you will use within
	Retro. This decorator allows to wrap an existing method and indicate that
	it will be used to process an HTTP request.

	The @on decorator can take `GET` and `POST` arguments, which take either a
	string or a list of strings, each describing an URI pattern (see
	@Dispatcher) that when matched, will trigger the method.

	The decorated method must take a `request` argument, as well as the same
	arguments as those used in the pattern.

	For instance:

	>	@on(GET='/list/{what:string}'

	implies that the wrapped method is like

	>	def listThings( self, request, what ):
	>		....

	it is also crucuial to return a a response at the end of the call:

	>		returns request.respond(...)

	The @Request class offers many methods to create and send responses."""
	def decorator(function):
		v = function.__dict__.setdefault(EXTRA_ON, [])
		function.__dict__.setdefault(EXTRA_ON_PRIORITY, priority)
		for http_method, url in list(methods.items()):
			if type(url) not in (list, tuple): url = (url,)
			for _ in url:
				v.append((http_method, _))
		return function
	return decorator

# TODO: We could have an extractor method that would extract sepcific parameters from
# the request body. Ex:
# @expose(POST="/api/ads", name=lambda _:_.get("name"), ....)
def expose( priority=0, compress=False, contentType=None, raw=False, **methods ):
	"""The @expose decorator is a variation of the @on decorator. The @expose
	decorator allows you to _expose_ an existing Python function as a JavaScript
	(or JSON) producing method.

	Basically, the @expose decorator allows you to automatically bind a method to
	an URL and to ensure that the result will be JSON-ified before being sent.
	This is perfect if you have an existing python class and want to expose it
	to the web."""
	def decorator(function):
		function.__dict__.setdefault(EXTRA_EXPOSE, True)
		function.__dict__.setdefault(EXTRA_EXPOSE_JSON, None)
		function.__dict__.setdefault(EXTRA_EXPOSE_RAW , raw)
		function.__dict__.setdefault(EXTRA_EXPOSE_COMPRESS, compress)
		function.__dict__.setdefault(EXTRA_EXPOSE_CONTENT_TYPE, contentType)
		# This is copy and paste of the @on body
		v = function.__dict__.setdefault(EXTRA_ON,   [])
		function.__dict__.setdefault(EXTRA_ON_PRIORITY, int(priority))
		for http_method, url in list(methods.items()):
			if type(url) not in (list, tuple): url = (url,)
			for _ in url:
				if http_method == "json":
					function.__dict__[EXTRA_EXPOSE_JSON] = _
				else:
					v.append((http_method, _))
		return function
	return decorator

def when( *predicates ):
	"""The @when(...) decorate allows to specify that the wrapped method will
	only be executed when the given predicate (decorated with `@on`)
	succeeds."""
	def decorator( function ):
		v = function.__dict__.setdefault(EXTRA_WHEN, [])
		v.extend(predicates)
		return function
	return decorator

class Handler:

	@classmethod
	def Has( cls, value ):
		return hasattr(value, EXTRA_ON)

	@classmethod
	def Get( cls, value ):
		return Handler(
			functor  = value,
			methods  = getattr(value, EXTRA_ON),
			priority = getattr(value, EXTRA_ON_PRIORITY),
			expose   = getattr(value, EXTRA_EXPOSE) if hasattr(value, EXTRA_EXPOSE) else None,
		) if cls.Has(value) else None

	def __init__( self, functor:Callable, methods:List[str], priority:int=0, expose:bool=False ):
		self.functor = functor
		self.methods = methods
		self.priority = priority
		self.expose = expose

	def __repr__( self ):
		methods = " ".join(f'({k} "{v}")' for k,v in self.methods)
		return f"(Handler {self.priority} ({methods}) '{self.functor}' {' :expose' if self.expose else ''})"

# EOF
