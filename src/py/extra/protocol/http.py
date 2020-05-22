from ..protocol import Request, Response
from typing import List,Any,Optional,Union

class HTTPRequest(Request):
	POOL:List['HTTPRequest'] = []

	def respond( self, value:Any, contentType:Optional[Union[str,bytes]]=None, status:int=200 ):
		return HTTPResponse.Create().init(status).setContent(value, contentType)

	def notFound( self ) -> 'HTTPResponse':
		return HTTPResponse.Create().init(status=404).setContent("Resource not found")


class HTTPResponse(Response):
	POOL:List['HTTPResponse'] = []

# EOF
