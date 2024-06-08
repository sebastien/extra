from extra import Service, on, run


class API(Service):
    @on(GET="/")
    def hello(self, request):
        return request.respondText(b"Hello, World!")


if __name__ == "__main__":
    run(API())

# EOF
