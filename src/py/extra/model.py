from .routing import Handler, Dispatcher
from .protocol import Request
from .protocol.http import HTTPRequest, HTTPResponse
from typing import Optional, Tuple, Iterable, Callable, List
import sys
import importlib

# -----------------------------------------------------------------------------
#
# SERVICE
#
# -----------------------------------------------------------------------------


class Service:
    PREFIX = ""
    NO_HANDLER = ["name", "app", "prefix", "_handlers",
                  "isMounted", "handlers", "start", "stop"]

    @classmethod
    def ReloadFrom(cls, service: 'Service') -> 'Service':
        res = cls(name=service.name)
        res.app = res.app
        # TODO: What about the prefix?
        return res

    def __init__(self, name: Optional[str] = None):
        self.name: str = name or self.__class__.__name__
        self.app: Optional[Application] = None
        self.prefix = self.PREFIX
        self._handlers: Optional[Tuple[Handler]] = None

    async def start(self):
        pass

    async def stop(self):
        pass

    @property
    def isMounted(self) -> bool:
        return self.app != None

    @property
    def handlers(self) -> Tuple[Handler]:
        if self._handlers is None:
            self._handlers = tuple(self.iterHandlers())
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
        self.routes = None
        self.dispatcher = Dispatcher()
        self.services = []

    def reload(self) -> 'Application':
        self.stop()
        # FIXME: We need to restore the service state/configuration
        services = []
        reloaded = []
        for service in self.services:
            parent_class = service.__class__
            parent_class_name = parent_class.__name__
            parent_module_name = parent_class.__module__
            parent_module = sys.modules[parent_module_name]
            if parent_module not in reloaded:
                reloaded.append(parent_module)
                parent_module = importlib.reload(parent_module_name)
            if hasattr(parent_module, parent_class_name):
                services.append(
                    getattr(parent_module, parent_class_name).ReloadFrom(service))
            else:
                raise KeyError(
                    f"Class {parent_class_name} is not defined in module {parent_module_name} anymore.")
        self.services = services
        self.start()

    async def start(self) -> 'Application':
        self.dispatcher.prepare()
        for service in self.services:
            await service.start()
        return self

    async def stop(self) -> 'Application':
        for service in self.services:
            await service.stop()
        return self

    def mount(self, service: Service, prefix: Optional[str] = None):
        assert not service.isMounted, f"Cannot mount service, it is already mounted: {service}"
        for handler in service.handlers:
            self.dispatcher.register(handler, prefix or service.prefix)
        return service

    def unmount(self, service: Service):
        assert service.isMounted, f"Cannot unmount service, it is not already mounted: {service}"
        assert service.app != self, f"Cannot unmount service, it is not mounted in this applicaition: {service}"
        service.app = self
        return service

    # TODO: Should process other types of request as well
    def process(self, request: HTTPRequest) -> HTTPResponse:
        # NOTE: That chunk should be pretty common across bridges
        route, params = self.dispatcher.match(request.method, request.path)
        if route:
            handler = route.handler
            assert handler, f"Route has no handler defined: {route}"
            response = handler(request, params)
        else:
            response = self.onRouteNotFound(request)
        return response

    def onRouteNotFound(self, request: Request):
        return request.notFound()

# EOF
