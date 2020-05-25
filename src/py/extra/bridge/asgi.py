from ..protocol import Request, Response
from ..protocol.http import HTTPRequest, HTTPResponse
from ..model import Service, Application
from typing import Dict,Callable,Any,Coroutine,Union,cast

# SEE: https://asgi.readthedocs.io/en/latest/specs/main.html

TScope = Dict[str,Any]
TSend  = Callable[[Dict[str,Any]],Coroutine]

class ASGIBridge:
	"""Creates `Request` object from the ASGI interface, and writes out
	`Response`objects to the ASGI interface."""

	async def read( self, scope:TScope, receive, app:Application ) -> Request:
		protocol   = scope["type"]
		if protocol == "http" or protocol == "https":
			# SEE: https://asgi.readthedocs.io/en/latest/specs/www.html
			# TODO: We should populate the request with the scope
			request =  HTTPRequest.Create().init()
			# NOTE: Not sure how it stacks against scope["scheme"]
			# We copy the attributes here
			request.protocol         = protocol
			request.version          = scope["http_version"]
			request.method           = scope["method"]
			request.path             = scope["path"]
			request.query            = scope["query_string"]
			# client: It's an Iterable[str,int]
			# server: It's an Iterable[str,int]
			for name, value in scope["headers"]:
				request.setHeader(name, value)
			return request
		elif protocol == "lifespan":
			# SEE: https://asgi.readthedocs.io/en/latest/specs/lifespan.html
			# It's not ideal to have it here
			while True:
				# FIXME: This is probably not idea
				message = await receive()
				if message["type"] == "lifespan.startup":
					# TODO: Handle startup
					await send({"type": "lifespan.startup.complete"})
				elif message["type"] == "lifespan.shutdown":
					# TODO: Handle shutdown
					await send({"type": "lifespan.shutdown.complete"})
					return
		else:
			raise ValueError(f"Unsupported protocol: {protocol}")

	async def write( self, scope:TScope, send, response:Response ):
		# FROM: https://asgi.readthedocs.io/en/latest/specs/www.html
		# Servers are responsible for handling inbound and outbound chunked
		# transfer encodings. A request with a chunked encoded body should be
		# automatically de-chunked by the server and presented to the
		# application as plain body bytes; a response that is given to the
		# server with no Content-Length may be chunked as the server sees fit.
		# Sending the start
		headers = [_ for _ in response.headers]
		await send({
			"type": "http.response.start",
			"status": response.status,
			"headers": headers
		})
		# Now we take care of the body
		bodies = response.bodies
		if not bodies:
			await send({
				"type":   "http.response.body",
				"status": response.status,
			})
		else:
			for value,contentType in bodies:
				await send({
					"type":   "http.response.body",
					"status": response.status,
					"body":   value,
				})

def serve(*services:Union[Application,Service]) -> Callable:
	"""Creates an ASGI bridge, mounts the services into an application
	and returns the ASGI application handler."""
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
		request = await bridge.read(scope, receive, app)
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
		response.recycle()
		request.recycle()
	return application

# EOF
