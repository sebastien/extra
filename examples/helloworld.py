from extra import Service, HTTPRequest, HTTPResponse, on, run


class HelloWorld(Service):
    @on(GET="{any}")
    def helloWorld(self, request: HTTPRequest, any: str) -> HTTPResponse:
        return request.respond(b"Hello, World !", b"text/plain")


if __name__ == "__main__":
    run(HelloWorld)

# EOF
