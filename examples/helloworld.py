from extra import Service, Request, Response, on, serve

class HelloWorld(Service):

	@on(GET="{any}")
	def sayHello( self, request:Request ) -> Response:
		return request.respond(b"Hello, world", b"text/plain")

# NOTE: You can start this with `uvicorn helloworld:app`
app = serve(HelloWorld)
# EOF
