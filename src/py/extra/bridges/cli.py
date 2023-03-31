from ..model import Service, Application
from ..bridge import mount
from ..protocol.http import HTTPRequest
from typing import Dict, Callable, Any, Coroutine, Union, Iterable


def server(
    *services: Union[Application, Service]
) -> Callable[[str, str], Iterable[bytes]]:

    app: Application = mount(*services)

    def run(method: str, path: str) -> Iterable[bytes]:
        route, params = app.dispatcher.match(method, path)
        request = HTTPRequest.Create()
        if route:
            handler = route.handler
            assert handler, f"Route has no handler defined: {route}"
            response = handler(request, params)
        else:
            response = app.onRouteNotFound(request)
        for chunk in response.read():
            yield chunk
        response.recycle()
        request.recycle()

    return run


# EOF
