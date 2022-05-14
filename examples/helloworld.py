from extra import Service, HTTPRequest, HTTPResponse, on, server, run


class HelloWorld(Service):
    @on(GET="{any}")
    def helloWorld(self, request: HTTPRequest, any: str) -> HTTPResponse:
        return request.respond(b"Hello, World !", b"text/plain")


run(HelloWorld)
# NOTE: You can start this with `uvicorn helloworld:app`
# app = server(HelloWorld)

# Otherwise executing the module directly makes it work
# if __name__ == "__main__":
#     run(app)

# EOF
