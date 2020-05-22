from .routing import Route
from .protocol import Request, Response
from .model import Service,Application
from .decorators import on, expose
from .bridge.asgi import serve as serve_asgi
from .bridge.cli import serve as serve_cli
from typing import Union, cast

def serve(*services:Union[Application,Service]):
	return serve_asgi(*services)

# EOF
