from extra import Service, expose
from extra.bridge.aio import run

# NOTE: This is like FastAPI's example
# https://fastapi.tiangolo.com/


class API(Service):
    @expose(GET="/")
    def hello(self):
        return {"Hello": "World"}


if __name__ == "__main__":
    run(API())

# EOF
