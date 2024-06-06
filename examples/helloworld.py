from extra import Service, HTTPRequest, HTTPResponse, on, run


class HelloWorld(Service):
    @on(GET="{rest}")
    def helloWorld(self, request: HTTPRequest, rest: str) -> HTTPResponse:
        return request.respond(b"XXXHello, World !", "text/plain")


if __name__ == "__main__":
    run(HelloWorld())

# EOF
