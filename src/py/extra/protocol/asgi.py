from .protocol import Request, Response, HTTPRequest, HTTPResponse, ValueBody, StreamBody, FileBody, IterableBody
from .model import Service, Application
from typing import Dict,Callable,Any,Coroutine,Union,cast

# SEE: https://asgi.readthedocs.io/en/latest/specs/main.html

TScope = Dict[str,Any]
TSend  = Callable[[Dict[str,Any]],Coroutine]

class ASGIBridge:
	"""Creates `Request` object from the ASGI interface, and writes out
	`Response`objects to the ASGI interface."""

	async def read( self, scope:TScope, receive ) -> Request:
		protocol   = scope["type"]
		if protocol == "http" or protocol == "https":
			# TODO: We should populate the request with the scope
			return HTTPRequest()
		else:
			raise ValueError(f"Unsupported protocol: {protocol}")

	async def write( self, scope:TScope, send, response:Response ):
		# Sending the start
		headers = [_ for _ in response.headers]
		await send({
			"type": "http.response.start",
			"status": response.status,
			"headers": headers
		})
		# Now we take care of the body
		body = response.body
		if body == None:
			await send({
				"type":   "http.response.body",
				"status": response.status,
			})
		elif isinstance(body, ValueBody):
			await send({
				"type":   "http.response.body",
				"status": response.status,
				"body":   response.body.value
			})
		else:
			raise ValueError("Unsupported body type")

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
		method  = scope["method"]
		path    = scope["path"]
		route, params = app.dispatcher.match(method, path)
		if route:
			handler = route.handler
			assert handler, f"Route has no handler defined: {route}"
			response = handler(request, params)
		else:
			response = app.onRouteNotFound(request)
		# Application processes response
		await bridge.write(scope, send, response)
	return application

# EOF
