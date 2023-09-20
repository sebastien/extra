from .routing import Route  # NOQA: F401
from .protocols import Request, Response  # NOQA: F401
from .protocols.http import HTTPRequest, HTTPResponse  # NOQA: F401
from .model import Service, Application
from .decorators import on, expose  # NOQA: F401
from .bridges import Bridge
from .bridges.aio import run as aio_run
from .logging import logger  # NOQA: F401
from typing import Union, Callable, Type  # NOQA: F401


def run(*components: Union[Application, Service]) -> Bridge:
    """Runs the given components"""
    return aio_run(*components)


# EOF
