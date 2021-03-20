from .routing import Route
from .protocol import Request, Response
from .protocol.http import HTTPRequest, HTTPResponse
from .model import Service, Application
from .decorators import on, expose
from .bridge.asgi import server as asgi_server
from .bridge.cli import server as cli_server
from .logging import info, warning, error
from typing import Union


def server(*services: Union[Application, Service]):
    return asgi_server(*services)

# EOF
