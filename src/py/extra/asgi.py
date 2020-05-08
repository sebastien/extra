from .http import Request, Response
from .model import Service, Application
from typing import Dict,Callable,Any,Coroutine,Union,cast

TScope = Dict[str,Any]
TSend  = Callable[[Dict[str,Any]],Coroutine]

class ASGIBridge:
	"""Creates `Request` object from the ASGI interface, and writes out
	`Response`objects to the ASGI interface."""

	async def read( self, scope:TScope, receive ) -> Request:
		return Request()

	async def write( self, scope:TScope, send, response:Response ):
		# Sending the start
		await send({
			"type": "http.response.start",
			"status": response.status,
			"headers": [
				[b'content-type', self.encode(response.contentType)]
			]
		})
		await send({
			"type":   "http.response.body",
			"status": response.status,
			"body":   b"Hello, world"
		})

	def encode( self, value:Union[str,bytes] ):
		return bytes(value, "utf8") if isinstance(value,str) else value

def serve(*services:Union[Application,Service]):
	bridge = ASGIBridge()
	# This extracts and instanciates the services and applications that
	# are given here.
	services = [_()  if isinstance(_, type) else _ for _ in services]
	app      = [_ for _ in services if isinstance(_, Application)]
	services = [_ for _ in services if isinstance(_, Service)]
	app      = cast(Application, app[0] if app else Application())
	# Now we mount all the services on the application
	for service in services:
		app.mount(service)
	app.start()
	# Ands we're ready for the main loop
	async def application(scope:TScope, receive, send):
		request = await bridge.read(scope, receive)
		# Application processes response
		response = Response(200, "text/plain")
		await bridge.write(scope, send, response)
	return application

# EOF
