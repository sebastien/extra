from typing import Optional,Callable,Dict,Tuple,Any,Iterable,List
from .decorators import EXTRA
import re

# -----------------------------------------------------------------------------
#
# ROUTE
#
# -----------------------------------------------------------------------------

class Route:

	RE_TEMPLATE = re.compile(r"\{([\w][_\w\d]*)(:([^}]+))?\}")
	RE_SPECIAL  = re.compile(r"/\+\*\-\:")

	PATTERNS:Dict[str,Tuple[str,Callable[[str],Any]]] = {
		'id'     : (r'[a-zA-Z0-9\-_]+' , str   ),
		'word'   : (r'\w+'       , str   ),
		'name'   : (r'\w[\-\w]*' , str   ),
		'alpha'  : (r'[a-zA-Z]+' , str   ),
		'string' : (r'[^/]+'     , str   ),
		'digits' : (r'\d+'       , int   ),
		'number' : (r'\-?\d*\.?\d+' , lambda x:x.find(".") != -1 and float(x) or int(x)),
		'int'    : (r'\-?\d+'       , int   ),
		'integer': (r'\-?\d+'       , int   ),
		'float'  : (r'\-?\d*.?\d+'  , float ),
		'file'   : (r'\w+(.\w+)' , str   ),
		'chunk'  : (r'[^/^.]+'   , str   ),
		'path'   : (r'[^:@]+'   , str   ),
		'segment': (r'[^/]+'     , str   ),
		'any'    : (r'.+'        , str   ),
		'rest'   : (r'.+'        , str   ),
		'range'  : (r'\-?\d*\:\-?\d*', lambda x:x.split(':')),
		'lang'   : (r"((\w\w)/)?", lambda x: x[:-1]),
	}

	@classmethod
	def AddType( cls, type:str, regexp:str, parser:Callable[[str],Any]=str ):
		# We do a precompilation to make sure it's working
		try:
			re.compile(regexp)
		except Exception as e:
			raise ValueError(f"Regular expression '{regexp}' is malformed: {e}")
		cls.PATTERNS[type.lower()] = (regexp, parser)
		return cls

	@classmethod
	def Parse( cls, expression:str, isStart=True ):
		"""Parses routes expressses as strings where patterns are denoted
		as `{name}` or `{name:pattern}`"""
		chunks = []
		offset = 0
		# We escape the special characters
		# escape = lambda _:cls.RE_SPECIAL.sub(lambda _:"\\" + _, _)
		for match in cls.RE_TEMPLATE.finditer(expression):
			chunks.append(('T', expression[offset:match.start()]))
			name = match.group(1)
			pattern = (match.group(3) or name).lower()
			if pattern not in cls.PATTERNS:
				raise ValueError(f"Route pattern '{pattern}' is not registered, pick one of: {', '.join(sorted(cls.PATTERNS.keys()))}")
			chunks.append(('P', name, cls.PATTERNS[pattern]))
			offset = match.end()
		chunks.append(('T', expression[offset:]))
		return chunks

# -----------------------------------------------------------------------------
#
# PREFIX
#
# -----------------------------------------------------------------------------

class Prefix:

	@classmethod
	def Make( self, values:Iterable[str] ):
		root = Prefix()
		for _ in values:
			root.register(_)
		return root.simplify()

	def __init__( self, value:Optional[str]=None, parent:Optional['Prefix']=None ):
		self.value = value
		self.parent = parent
		self.children:Dict[str,Prefix] = {}

	def simplify( self ):
		simplified:Dict[str,Prefix] = {}
		return self

	def register( self, text:str ):
		c, rest = text[0], text[1:]
		if c not in self.children:
			self.children[c] = Prefix(c, self)
		if rest:
			self.children[c].register(rest)

	def __repr__( self ):
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
	def Has( cls, value ):
		return hasattr(value, EXTRA.ON)

	@classmethod
	def Get( cls, value ):
		return Handler(
			functor  = value,
			methods  = getattr(value, EXTRA.ON),
			priority = getattr(value, EXTRA.ON_PRIORITY),
			expose   = getattr(value, EXTRA.EXPOSE) if hasattr(value, EXTRA.EXPOSE) else None,
		) if cls.Has(value) else None

	def __init__( self, functor:Callable, methods:List[str], priority:int=0, expose:bool=False ):
		self.functor = functor
		self.methods = methods
		self.priority = priority
		self.expose = expose

	def __repr__( self ):
		methods = " ".join(f'({k} "{v}")' for k,v in self.methods)
		return f"(Handler {self.priority} ({methods}) '{self.functor}' {' :expose' if self.expose else ''})"

# -----------------------------------------------------------------------------
#
# DISPATCHER
#
# -----------------------------------------------------------------------------

class Dispatcher:

	def __init__( self ):
		self.prefixes:Dict[str,Prefix] = {}

	def register( self, handler:Handler, prefix:Optional[str]=None ):
		print ("HANDLER", handler)
		for method, path in handler.methods:
			route = Route.Parse(prefix + path if prefix else path)
			print (path, route)

	def match( self, path ) -> Optional[Handler]:
		pass

# EOF
