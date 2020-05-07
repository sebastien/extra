# TODO: Use Hypercorn, uvicorn
from typing import Any,Optional

class WithHeaders:

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
	def contentType( self ):
		pass

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
	def headers( self ):
		pass

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

	def respond( self ):
		pass

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

class Response:

	def __init__( self, status:int, contentType:str ):
		self.status = status
		self.contentType = contentType

	def setCookie( self, name:str, value:Any ):
		pass

	def setHeader( self, name:str, value:Any ):
		pass

class HTTPResponse(Response):
	pass

class WebSocketResponse(Response):
	pass

# EOF
