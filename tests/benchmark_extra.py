from extra import server, expose, Service

# NOTE: This is like FastAPI's example
# https://fastapi.tiangolo.com/


class API(Service):

    @expose(GET="/")
    def hello(self):
        return {"Hello": "World"}


# To run: uvicorn benchmark_api:app
app = server(API())

# EOF
