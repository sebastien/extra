from extra import Service, HTTPRequest, HTTPResponse, on, run


class HelloWorld(Service):
    def __init__(self):
        super().__init__()
        self.count: int = 0

    @on(GET="{any}")
    def helloWorld(self, request: HTTPRequest, any: str) -> HTTPResponse:
        self.count += 1
        return request.respond(f"Hello, World ! #{self.count}", "text/plain")


if __name__ == "__main__":
    run(HelloWorld())

# EOF
