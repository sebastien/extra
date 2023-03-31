from .routing import Route
from .protocols import Request, Response
from .protocols.http import HTTPRequest, HTTPResponse
from .model import Service, Application
from .decorators import on, expose
from .bridges import Bridge
from .bridges.aio import run as aio_run
from .logging import logger
from typing import Union, Callable, Type


def run(*components: Union[Application, Service]) -> Bridge:
    """Runs the given components"""
    return aio_run(*components)


# EOF
