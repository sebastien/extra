# TODO: Use Hypercorn, uvicorn
from typing import Any,Optional,Iterable,Any,Tuple,Union,Dict,TypeVar,Generic,List,NamedTuple
from enum import Enum

T = TypeVar('T')

ContentType   = b'Content-Type'
ContentLength = b'Content-Length'

def encode( value:Union[str,bytes] ) -> bytes:
	return bytes(value, "utf8") if isinstance(value,str) else value

class Flyweight:

	@classmethod
	def Recycle( cls, value ):
		cls.POOL.append(value)

	@classmethod
	def Create( cls ):
		return cls.POOL.pop() if cls.POOL else cls()

	def init( self ):
		return self

	def reset( self ):
		return self

	def recycle( self ):
		self.reset()
		self.__class__.POOL.append(self)

# NOTE: We use byte strings here directly to
class WithHeaders:

	def __init__( self ):
		self._headers:Dict[bytes,Any] = {}

	@property
	def userAgent( self ):
		pass

	@property
	def host( self ):
		pass

	@property
	def contentLength( self ):
		pass

	@property
	def contentType( self ) -> bytes:
		return self._headers.get(ContentType)

	@contentType.setter
	def contentType( self, value:Union[str,bytes] ):
		self._headers[ContentType] = encode(value)

	@property
	def range( self ):
		pass

	@property
	def clientIP( self ):
		pass

	@property
	def clientPort( self ):
		pass

	@property
	def compression( self ):
		pass

	@property
	def headers( self ) -> Iterable[Tuple[bytes,bytes]]:
		return self._headers.items()

	def getHeader( self, name:str  ) -> Any:
		pass

class WithCookies:

	# @group Cookies

	@property
	def cookies( self ):
		pass

	def getCookie( self, name:str  ) -> Any:
		pass

class Request(WithHeaders, WithCookies, Flyweight):

	# @group Request attributes

	def __init__( self ):
		WithHeaders.__init__( self )
		WithCookies.__init__( self )
		Flyweight.__init__( self )

	def reset(self):
		self._headers.clear()

	@property
	def method( self ):
		pass

	@property
	def path( self ):
		pass

	@property
	def query( self ):
		pass

	@property
	def params( self ):
		pass

	@property
	def uri( self ):
		pass

	# @group Params

	@property
	def params( self ):
		pass

	def getParam( self, name:str  ) -> Any:
		pass

	# @group Loading

	@property
	def isLoaded( self ):
		pass

	@property
	def loadProgress( self ):
		pass

	def load( self  ) -> Any:
		pass

	# @group Files

	@property
	def files( self ):
		pass

	def getFile( self, name:str  ) -> Any:
		pass

	# @group Responses
	def multiple( self ):
		pass

	def redirect( self ):
		pass

	def bounce( self ):
		pass

	def returns( self ):
		pass

	def stream( self ):
		pass

	def local( self ):
		pass

	# @group Errors

	def notFound( self ):
		pass

	def notAuthorized( self ):
		pass

	def notModified( self ):
		pass

	def fail( self ):
		pass


BodyType = Enum("BodyType", "none value iterator")
Body     = NamedTuple("Body", [("type", BodyType), ("content", Union[bytes]), ("contentType", bytes)])

class Response(WithHeaders, WithCookies, Flyweight):

	def __init__( self ):
		WithHeaders.__init__( self )
		WithCookies.__init__( self )
		Flyweight.__init__( self )
		self.status = -1
		self.bodies = []

	def init( self, status:int ):
		self.status = status
		return self

	def reset( self ):
		self.bodies.clear()

	def setCookie( self, name:str, value:Any ):
		pass

	def setHeader( self, name:str, value:Any ):
		pass

	def setContent( self, content:Union[str,bytes], contentType:Optional[Union[str,bytes]]=None) -> 'Response':
		if isinstance(content, str):
			# SEE: https://www.w3.org/International/articles/http-charset/index
			self.bodies.append((encode(content), b"text/plain; charset=utf-8"))
		elif isinstance(content, bytes):
			self.bodies.append((content, encode(contentType or b"application/binary")))
		else:
			raise ValueError("Content type not supported, choose 'str' or 'bytes': {content}")
		return self

	def read( self ) -> Iterable[Union[bytes,None]]:
		yield None
		pass

# EOF
