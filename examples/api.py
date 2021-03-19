from extra import Service, Request, Response, on, expose, serve
import time

# @title API Example


class API(Service):

    PREFIX = "api"

    # @p Using `expose` automatically exposes the method through the web
    # service, encoding the results as JSON
    @expose(GET="time")
    def time(self):
        return time.time()

    # @p Adding an `init` method allows for initialising the state of the
    # service.
    def init(self):
        self.count = 0

    @expose(GET="counter")
    async def counter(self):
        return self.count

    # @p The route syntax supports types that will be automatically mapped
    # to the handler's argumentsj
    @expose(GET="counter/add/{count:int}")
    async def increment(self, count: int):
        self.count += count
        return self.count

    # @p The `on` decorator adds the request as the first argument but
    # also expectes a response as a return value.
    #
    # Note the `GET_POST` syntax that denotes that we're supporting both
    # `GET` and `POST` methods.
    @on(GET_POST="pong")
    async def pong(self, request: Request) -> Response:
        await request.load()
        return request.returns(request.data)


# NOTE: You can start this with `uvicorn helloword:app`
app = serve(API)
# EOF
