from .routing import Route
from .protocol import Request, Response
from .protocol.http import HTTPRequest, HTTPResponse
from .model import Service, Application
from .decorators import on, expose
from .bridge import Bridge
from .bridge.aio import run as aio_run
from .logging import logger
from typing import Union, Callable, Type


def run(*components: Union[Application, Service]) -> Bridge:
    """Runs the given components"""
    return aio_run(*components)


# EOF
