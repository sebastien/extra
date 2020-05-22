# TODO: Use Hypercorn, uvicorn
from typing import Any,Optional,Iterable,Any,Tuple,Union,Dict,TypeVar,Generic,List

T = TypeVar('T')

ContentType   = b'Content-Type'
ContentLength = b'Content-Length'

def encode( value:Union[str,bytes] ) -> bytes:
	return bytes(value, "utf8") if isinstance(value,str) else value

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

class Request(WithHeaders, WithCookies):

	# @group Request attributes

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

	def respond( self, value:Any, contentType:Optional[Union[str,bytes]]=None, status:int=200 ):
		return HTTPResponse(status).setContent(value, contentType)

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


class Body(Generic[T]):

	def __init__( self, value:T, contentType:bytes ):
		self.value = value
		self.contentType = contentType

class ValueBody(Body[bytes]):
	pass

class StreamBody(Body):
	pass

class FileBody(Body):
	pass

class IterableBody(Body):
	pass

class Response(WithHeaders, WithCookies):

	def __init__( self, status:int ):
		WithHeaders.__init__( self )
		self.status = status
		self.body:Optional[Body] = None

	def setCookie( self, name:str, value:Any ):
		pass

	def setHeader( self, name:str, value:Any ):
		pass

	def setContent( self, content:Union[str,bytes], contentType:Optional[Union[str,bytes]]=None) -> 'HTTPResponse':
		if isinstance(content, str):
			# SEE: https://www.w3.org/International/articles/http-charset/index
			self.body = ValueBody(encode(content), b"text/plain; charset=utf-8")
		elif isinstance(content, bytes):
			self.body = ValueBody(content, encode(contentType or b"application/binary"))
		else:
			raise ValueError("Content type not supported, choose 'str' or 'bytes': {content}")
		return self

	def read( self ) -> Iterable[Union[bytes,None]]:
		yield None
		pass

class HTTPResponse(Response):
	pass

class WebSocketResponse(Response):
	pass

# EOF
