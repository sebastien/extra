from ..protocol import Request, Response
from typing import List,Any,Optional,Union

class HTTPRequest(Request):
	POOL:List['HTTPRequest'] = []

	# @group(Responses)
	def __init__( self ):
		super().__init__()
		self.protocol = "http"
		self.protocolVersion = "1.0"
		self.method = "GET"
		self.path   = ""
		self.query:Optional[str]   = None
		self.ip:Optional[str]     = None
		self.port:Optional[int]   = None

	def respond( self, value:Any, contentType:Optional[Union[str,bytes]]=None, status:int=200 ):
		return HTTPResponse.Create().init(status).setContent(value, contentType)

	def respondFile( self ):
		return HTTPResponse.Create().init(status).fromFile()

	def respondStream( self ):
		return HTTPResponse.Create().init(status).fromStream()

	# @group(Errors)

	def notFound( self ) -> 'HTTPResponse':
		return HTTPResponse.Create().init(status=404).setContent("Resource not found")

class HTTPResponse(Response):
	POOL:List['HTTPResponse'] = []

	def fromFile( self ):
		pass

	def fromStream( self ):
		pass

# EOF
