from extra import Service, HTTPRequest, HTTPResponse, on


class HelloWorld(Service):
    @on(GET="{any}")
    def helloWorld(self, request: HTTPRequest, any: str) -> HTTPResponse:
        return request.respond(b"Hello, World !", b"text/plain")


run(HelloWorld)
