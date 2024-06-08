from extra import Service, HTTPRequest, HTTPResponse, on, expose, run
import time

# --
# # Extra API Example


class API(Service):

    PREFIX = "api/"

    # --
    # Using `expose` automatically exposes the method through the web
    # service, encoding the results as JSON
    @expose(GET="time")
    def time(self):
        """Returns the local time"""
        return time.time()

    # --
    # Adding an `init` method allows for initialising the state of the
    # service.
    def init(self):
        self.count = 0

    @expose(GET="counter")
    async def counter(self):
        """Returns the value of the given counter"""
        return self.count

    # --
    # The route syntax supports types that will be automatically mapped
    # to the handler's arguments.
    @expose(GET="counter/add/{count:int}")
    async def increment(self, count: int):
        """Increments the counter by `count`. See `counter`."""
        self.count += count
        return self.count

    # --
    # The `on` decorator adds the request as the first argument but
    # also expects a response as a return value.
    #
    # Note the `GET_POST` syntax that denotes that we're supporting both
    # `GET` and `POST` methods.
    @on(GET_POST="pong")
    async def pong(self, request: HTTPRequest) -> HTTPResponse:
        """Returns the contents of the request as-as, encoded as JSON"""
        await request.load()
        return request.returns(request.data)


if __name__ == "__main__":
    app = run(API())

# EOF
