import functools
from typing import List, Callable

class EXTRA:
	ON                   = "_extra_on"
	ON_PRIORITY          = "_extra_on_priority"
	EXPOSE               = "_extra_expose"
	EXPOSE_JSON          = "_extra_expose_json"
	EXPOSE_RAW           = "_extra_expose_raw"
	EXPOSE_COMPRESS      = "_extra_expose_compress"
	EXPOSE_CONTENT_TYPE  = "_extra_expose_content_type"
	WHEN                 = "_extra_when"

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

	it is also crucial to return a a response at the end of the call:

	>		returns request.respond(...)

	The @Request class offers many methods to create and send responses."""
	def decorator(function):
		v = function.__dict__.setdefault(EXTRA.ON, [])
		function.__dict__.setdefault(EXTRA.ON_PRIORITY, priority)
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
		function.__dict__.setdefault(EXTRA.EXPOSE, True)
		function.__dict__.setdefault(EXTRA.EXPOSE_JSON, None)
		function.__dict__.setdefault(EXTRA.EXPOSE_RAW , raw)
		function.__dict__.setdefault(EXTRA.EXPOSE_COMPRESS, compress)
		function.__dict__.setdefault(EXTRA.EXPOSE_CONTENT_TYPE, contentType)
		# This is copy and paste of the @on body
		v = function.__dict__.setdefault(EXTRA.ON,   [])
		function.__dict__.setdefault(EXTRA.ON_PRIORITY, int(priority))
		for http_method, url in list(methods.items()):
			if type(url) not in (list, tuple):
				url = (url,)
			for method in http_method.upper().split("_"):
				for _ in url:
					if method == "JSON":
						function.__dict__[EXTRA.EXPOSE_JSON] = _
					else:
						v.append((method, _))
		return function
	return decorator

def when( *predicates ):
	"""The @when(...) decorate allows to specify that the wrapped method will
	only be executed when the given predicate (decorated with `@on`)
	succeeds."""
	def decorator( function ):
		v = function.__dict__.setdefault(EXTRA.WHEN, [])
		v.extend(predicates)
		return function
	return decorator


# EOF
