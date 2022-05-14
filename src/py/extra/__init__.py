from .routing import Route
from .protocol import Request, Response
from .protocol.http import HTTPRequest, HTTPResponse
from .model import Service, Application
from .decorators import on, expose
from .bridge.asgi import server as asgi_server
from .bridge.cli import server as cli_server
from .bridge.aio import run as aio_run
from .logging import logger
from typing import Union, Callable


# NOTE: Do  a proper typing of servers
def server(*services: Union[Application, Service]) -> Callable:
    return asgi_server(*services)


def run(*services: Union[Application, Service]):
    aio_run(*services)


# EOF
