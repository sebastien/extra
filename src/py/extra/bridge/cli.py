from ..protocol import Request, Response, StreamBody, FileBody, IterableBody, ValueBody
from ..protocol.http import HTTPRequest
from ..model import Service, Application
from ..bridge import mount
from typing import Dict,Callable,Any,Coroutine,Union,cast,Iterable

def serve(*services:Union[Application,Service]):
	app = mount(services)
	def run(method:str, path:str) -> Iterable[bytes]:
		route, params = app.dispatcher.match(method, path)
		request = HTTPRequest()
		if route:
			handler = route.handler
			assert handler, f"Route has no handler defined: {route}"
			response = handler(request, params)
		else:
			response = app.onRouteNotFound(request)
		for chunk in response.read():
			yield chunk
	return run

# EOF
