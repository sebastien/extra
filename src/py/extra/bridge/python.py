from typing import Union
from ..bridge import Bridge, mount
from ..model import Application, Service
from ..protocol.http import HTTPRequest, HTTPResponse, HTTPParser


class PythonBridge(Bridge):
    pass


def run(
    *services: Union[Application, Service],
) -> PythonBridge:
    return PythonBridge(mount(*services))


# EOF
