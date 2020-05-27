from extra import serve, expose, Service

# NOTE: This is like FastAPI's example
# https://fastapi.tiangolo.com/
class API(Service):

	@expose(GET="/")
	def root(self):
		return {"Hello": "World"}

	@expose(GET="/items/{item_id:int}")
	def readItem(self, item_id:int, q:str = None):
		return {"item_id": item_id, "q": q}

app = serve(API())

# EOF
