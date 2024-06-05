from .routing import Handler, Dispatcher, Route
from .protocols.http import HTTPRequest, HTTPResponse
from .decorators import Extra
from .logging import Logger
from typing import Optional, Iterable, ClassVar, Any
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
    PREFIX: ClassVar[str] = ""
    NO_HANDLER: ClassVar[list[str]] = [
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

    def __init__(self, name: Optional[str] = None, *, prefix: str | None = None):
        self.name: str = name or self.__class__.__name__
        self.app: Optional[Application] = None
        self.prefix = prefix or self.PREFIX
        self._handlers: Optional[list[Handler]] = None
        self.init()

    def init(self):
        pass

    async def start(self):
        pass

    async def stop(self):
        pass

    @property
    def isMounted(self) -> bool:
        return self.app is not None

    @property
    def handlers(self) -> list[Handler]:
        if self._handlers is None:
            self._handlers = list(self.iterHandlers())
        return self._handlers

    def iterHandlers(self) -> Iterable[Handler]:
        for value in (getattr(self, _) for _ in dir(self) if _ not in self.NO_HANDLER):
            handler = Handler.Get(value, extra=Extra.Meta(self.__class__))
            if handler:
                yield handler

    def __repr__(self) -> str:
        return f"(Service {self.name}{' :mounted' if self.isMounted else ''})"


# -----------------------------------------------------------------------------
#
# SECTION
#
# -----------------------------------------------------------------------------


class Application:
    def __init__(self, services: list[Service] | None = None) -> None:
        self.routes: list[Route] = []
        self.dispatcher: Dispatcher = Dispatcher()
        self.services: list[Service] = services if services else []

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
        for i, srv in enumerate(self.services):
            try:
                await srv.start()
            except Exception as e:
                logging.error(
                    "APPSTART",
                    f"Exception occurred when starting service #{i} {srv}: {e}",
                )
                raise e from e
        return self

    async def stop(self) -> "Application":
        for i, srv in enumerate(self.services):
            try:
                await srv.stop()
            except Exception as e:
                logging.error(
                    "APPSTART",
                    f"Exception occurred when stopping service #{i} {srv}: {e}",
                )
                raise e from e
        return self

    def process(self, request: HTTPRequest) -> HTTPResponse:
        route, params = self.dispatcher.match(
            request.method or "GET", request.path or "/"
        )
        if route:
            handler = route.handler
            if not handler:
                raise RuntimeError(f"Route has no handler defined: {route}")
            return handler(request, {} if params is True else params if params else {})
        else:
            return self.onRouteNotFound(request)

    def mount(self, service: Service, prefix: Optional[str] = None):
        if service.isMounted:
            raise RuntimeError(
                f"Cannot mount service, it is already mounted: {service}"
            )
        for handler in service.handlers:
            self.dispatcher.register(handler, prefix or service.prefix)
        return service

    def unmount(self, service: Service):
        if not service.isMounted:
            raise RuntimeError(
                f"Cannot unmount service, it is not already mounted: {service}"
            )
        if service.app == self:
            raise RuntimeError(
                f"Cannot unmount service, it is not mounted in this application: {service}"
            )
        service.app = self
        return service

    def onRouteNotFound(self, request: HTTPRequest):
        return request.notFound()


# EOF
