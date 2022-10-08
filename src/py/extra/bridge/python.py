from typing import Union
from ..bridge import Bridge, components
from ..model import Application, Service
from ..protocol.http import HTTPRequest, HTTPResponse, HTTPParser


class PythonBridge(Bridge):
    pass


def run(
    *services: Union[Application, Service],
) -> PythonBridge:
    """Runs the given services/application using the embedded AsyncIO HTTP server."""
    return PythonBridge(components(*services).app)


# EOF
