from extra import Service, HTTPRequest, HTTPResponse, on
from extra.bridge.python import run


class HelloWorld(Service):
	@on(GET="{any}")
	def helloWorld(self, request: HTTPRequest, any: str) -> HTTPResponse:
		return request.respond(b"Hello, World !", b"text/plain")


REQUEST = b"""\
GET /any HTTP/1.1\r
Host: localhost\r
Connection: keep-alive"""

RESPONSE = b"""\
HTTP/1.1 200 OK\r
Hello, World!"""


server = run(HelloWorld)
response = server.request(REQUEST)

assert b"".join(_ for _ in response) == RESPONSE

# EOF
