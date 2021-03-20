from extra import Service, HTTPRequest, HTTPResponse, on, server


class HelloWorld(Service):

    @on(GET="{any}")
    def helloWorld(self, request: HTTPRequest, any: str) -> HTTPResponse:
        return request.respond(b"Hello, World !", b"text/plain")


# NOTE: You can start this with `uvicorn helloworld:app`
app = server(HelloWorld)

# EOF
