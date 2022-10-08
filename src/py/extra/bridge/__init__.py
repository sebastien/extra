from typing import Union, NamedTuple, Optional, cast
from io import BytesIO
from ..model import Service, Application
from ..protocol.http import HTTPRequest, HTTPResponse, HTTPParser


class Bridge:
    def __init__(self, application: Application):
        self.application: Application = application
        if not self.application:
            raise ValueError("Bridge has not been given an application")

    def process(self, request: HTTPRequest) -> HTTPResponse:
        response = self.application.process(request)
        return response

    def requestBytes(self, request: bytes) -> HTTPResponse:
        # FIXME: Port should be sourced from somewhere else
        http_parser = HTTPParser("0.0.0.0", 80, {})
        read = http_parser.feed(request)
        request = HTTPRequest.Create().init(
            method=http_parser.method,
            path=http_parser.uri,
        )
        if http_parser.rest:
            request.feed(http_parser.rest)
        if not request.isInitialized:
            raise RuntimeError(f"Request is not initialized {request}")
            print("FAILED!", request)
        return self.process(request)

    def requestStream(self, reader: BytesIO):
        raise NotImplementedError


class Components(NamedTuple):
    @staticmethod
    def Make(components: Union[Application, Service, type[Application], type[Service]]):
        apps: list[Application] = []
        services: list[Service] = []
        for item in components:
            value: Union[Application, Service] = (
                item() if isinstance(item, type) else item
            )
            if isinstance(value, Application):
                apps.append(value)
            elif isinstance(value, Service):
                services.append(value)
            else:
                raise RuntimeError(f"Unsupported component type {type(value)}: {value}")
        return Components(apps[0] if apps else Application(), apps, services)

    app: Optional[Application]
    apps: list[Application]
    services: list[Application]


def components(
    *components: Union[Application, Service, type[Application], type[Service]]
) -> Components:
    return Components.Make(components)


def mount(
    *components: Union[Application, Service, type[Application], type[Service]]
) -> Application:
    c = Components.Make(components)
    app: Application = c.app or Application()
    # Now we mount all the services on the application
    for service in services:
        app.mount(service)
    # app.start()
    return app


# EOF
