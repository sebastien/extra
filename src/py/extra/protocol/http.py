from ..protocol import Request, Response

class HTTPRequest(Request):

	def notFound( self ) -> 'HTTPResponse':
		return HTTPResponse(status=404).setContent("Resource not found")


class HTTPResponse(Response):
	pass

# EOF
