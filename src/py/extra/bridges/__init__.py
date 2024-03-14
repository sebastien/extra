from typing import Union, NamedTuple, Optional, Iterable
from io import BytesIO
from types import GeneratorType
from ..model import Service, Application
from ..protocols.http import HTTPRequest, HTTPResponse, HTTPParser
from ..utils.config import HOST, PORT


class Bridge:
    """Bridges in Extra act as an interface (or a bridge) between the
    HTTP client and the underlying service infrastructure, whether it's
    a socket, a file or an API. The bridge is the foundation for Extra's
    modularity."""

    def __init__(self, application: Application):
        self.application: Application = application
        if not self.application:
            raise ValueError("Bridge has not been given an application")

    def process(self, request: HTTPRequest) -> HTTPResponse:
        response = self.application.process(request)
        return response

    def request(self, request: Union[bytes, BytesIO]) -> HTTPResponse:
        if isinstance(request, bytes):
            return self.requestFromBytes(request)
        else:
            return self.requestFromStream(request)

    def requestFromBytes(
        self, data: bytes, *, host: str = HOST, port: int = PORT
    ) -> HTTPResponse:
        # FIXME: Port should be sourced from somewhere else
        http_parser = HTTPParser(host, port, {})
        _ = http_parser.feed(data)
        request: HTTPRequest = HTTPRequest.Create().init(
            method=http_parser.method,
            path=http_parser.uri,
        )
        if http_parser.rest:
            request.feed(http_parser.rest)
        if not request.isInitialized:
            raise RuntimeError(f"Request is not initialized {request}")
        return self.process(request)

    def requestFromStream(self, reader: BytesIO):
        raise NotImplementedError


def flatten(value):
    if (
        isinstance(value, list)
        or isinstance(value, tuple)
        or isinstance(value, GeneratorType)
    ):
        for _ in value:
            yield from flatten(_)
    else:
        yield value


class Components(NamedTuple):
    """Groups Application and Service objects together"""

    @staticmethod
    def Make(components: Iterable[Union[Application, Service]]):
        apps: list[Application] = []
        services: list[Service] = []
        for item in flatten(components):
            if isinstance(item, Application):
                apps.append(item)
            elif isinstance(item, Service):
                services.append(item)
            else:
                raise RuntimeError(f"Unsupported component type {type(item)}: {item}")
        return Components(apps[0] if apps else Application(), apps, services)

    app: Optional[Application]
    apps: list[Application]
    services: list[Service]


def components(*components: Union[Application, Service]) -> Components:
    return Components.Make(components)


def mount(*components: Union[Application, Service]) -> Application:
    """Mounts the given components into ana application"""
    c = Components.Make(components)
    app: Application = c.app
    # Now we mount all the services on the application
    for service in c.services:
        app.mount(service)
    return app


# EOF
