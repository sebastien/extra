from extra import Service, Request, Response, on, serve


class HelloWorld(Service):

    @on(GET="{any}")
    def sayHello(self, request: Request, any: str) -> Response:
        return request.respond(bytes(f"Hello, route '{any}'", "utf8"), b"text/plain")


# NOTE: You can start this with `uvicorn helloworld:app`
app = serve(HelloWorld)

# EOF
