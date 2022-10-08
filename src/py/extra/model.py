from .routing import Handler, Dispatcher, Route
from .protocol.http import HTTPRequest, HTTPResponse
from .logging import Logger
from typing import Optional, Iterable, Callable, Any
import sys
import importlib
import asyncio

logging: Logger = Logger.Instance()

# -----------------------------------------------------------------------------
#
# SERVICE
#
# -----------------------------------------------------------------------------


class Service:
    PREFIX = ""
    NO_HANDLER = [
        "name",
        "app",
        "prefix",
        "_handlers",
        "isMounted",
        "handlers",
        "start",
        "stop",
    ]

    @classmethod
    def ReloadFrom(cls, service: "Service") -> "Service":
        res = cls(name=service.name)
        res.app = res.app
        # TODO: What about the prefix?
        return res

    def __init__(self, name: Optional[str] = None):
        self.name: str = name or self.__class__.__name__
        self.app: Optional[Application] = None
        self.prefix = self.PREFIX
        self._handlers: Optional[list[Handler]] = None

    async def start(self):
        pass

    async def stop(self):
        pass

    @property
    def isMounted(self) -> bool:
        return self.app != None

    @property
    def handlers(self) -> list[Handler]:
        if self._handlers is None:
            self._handlers = list(self.iterHandlers())
        return self._handlers

    def iterHandlers(self) -> Iterable[Handler]:
        for value in (getattr(self, _) for _ in dir(self) if _ not in self.NO_HANDLER):
            handler = Handler.Get(value)
            if handler:
                yield handler

    def __repr__(self):
        return f"(Service {self.name} {' :mounted' if self.isMounted else ''})"


# -----------------------------------------------------------------------------
#
# SECTION
#
# -----------------------------------------------------------------------------


class Application:
    def __init__(self):
        self.routes: list[Route] = None
        self.dispatcher = Dispatcher()
        self.services: list[Service] = []

    async def reload(self) -> "Application":
        await self.stop()
        # FIXME: We need to restore the service state/configuration
        services: list[Service] = []
        reloaded: list[Any] = []
        for service in self.services:
            parent_class: type = service.__class__
            parent_class_name: str = parent_class.__name__
            parent_module_name: str = parent_class.__module__
            parent_module: Any = sys.modules[parent_module_name]
            if parent_module not in reloaded:
                reloaded.append(parent_module)
                parent_module = importlib.reload(parent_module)
            if hasattr(parent_module, parent_class_name):
                services.append(
                    getattr(parent_module, parent_class_name).ReloadFrom(service)
                )
            else:
                raise KeyError(
                    f"Class {parent_class_name} is not defined in module {parent_module_name} anymore."
                )
        self.services = services
        await self.start()
        return self

    async def start(self) -> "Application":
        self.dispatcher.prepare()
        for i, res in enumerate(
            asyncio.gather(*(_.start() for _ in self.services), return_exceptions=True)
        ):
            if isinstance(res, Exception):
                logging.error(
                    "APPSTART",
                    "Exception occurred when starting service {self.services[i]}: {res}",
                )
        return self

    async def stop(self) -> "Application":
        for i, res in enumerate(
            asyncio.gather(*(_.stop() for _ in self.services), return_exceptions=True)
        ):
            if isinstance(res, Exception):
                logging.error(
                    "APPSTOP",
                    "Exception occurred when stopping service {self.services[i]}: {res}",
                )
        return self

    def process(self, request: HTTPRequest) -> HTTPResponse:
        route, params = self.dispatcher.match(
            request.method or "GET", request.path or "/"
        )
        if route:
            handler = route.handler
            assert handler, f"Route has no handler defined: {route}"
            return handler(request, params)
        else:
            return self.onRouteNotFound(request)

    def mount(self, service: Service, prefix: Optional[str] = None):
        assert (
            not service.isMounted
        ), f"Cannot mount service, it is already mounted: {service}"
        for handler in service.handlers:
            self.dispatcher.register(handler, prefix or service.prefix)
        return service

    def unmount(self, service: Service):
        assert (
            service.isMounted
        ), f"Cannot unmount service, it is not already mounted: {service}"
        assert (
            service.app != self
        ), f"Cannot unmount service, it is not mounted in this applicaition: {service}"
        service.app = self
        return service

    def onRouteNotFound(self, request: HTTPRequest):
        return request.notFound()


# EOF
