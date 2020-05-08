from .routing import Handler, Dispatcher
from typing import Optional,Tuple,Iterable,Callable,List

# -----------------------------------------------------------------------------
#
# SERVICE
#
# -----------------------------------------------------------------------------

class Service:
	PREFIX = ""
	NO_HANDLER = ["name", "app", "prefix", "_handlers", "isMounted", "handlers", "start", "stop"]

	def __init__( self, name:Optional[str]=None ):
		self.name:str = name or self.__class__.__name__
		self.app:Optional[Application] = None
		self.prefix = self.PREFIX
		self._handlers:Optional[Tuple[Handler]] = None

	def start( self ):
		pass

	def stop( self ):
		pass


	@property
	def isMounted( self ) -> bool:
		return self.app != None

	@property
	def handlers( self ) -> Tuple[Handler]:
		if self._handlers is None:
			self._handlers = tuple(self.iterHandlers())
		return self._handlers

	def iterHandlers( self ) -> Iterable[Handler]:
		for value in (getattr(self,_) for _ in dir(self) if _ not in self.NO_HANDLER):
			handler = Handler.Get(value)
			if handler:
				yield handler

	def __repr__( self ):
		return f"(Service {self.name} {' :mounted' if self.isMounted else ''})"

# -----------------------------------------------------------------------------
#
# SECTION
#
# -----------------------------------------------------------------------------

class Application:

	def __init__( self ):
		self.routes = None
		self.dispatcher = Dispatcher()
		self.services = []

	def start( self ):
		self.dispatcher.prepare()
		for service in self.services:
			service.start()

	def stop( self ):
		for service in self.services:
			service.stop()

	def mount( self, service:Service, prefix:Optional[str]=None ):
		assert not service.isMounted, f"Cannot mount service, it is already mounted: {service}"
		for handler in service.handlers:
			self.dispatcher.register(handler, prefix or service.prefix)
		return service

	def unmount( self, service:Service ):
		assert service.isMounted, f"Cannot unmount service, it is not already mounted: {service}"
		assert service.app != self, f"Cannot unmount service, it is not mounted in this applicaition: {service}"
		service.app = self
		return service

	def match( self, method:str, path:str ):
		match = self.dispatcher.match(method, path)
		if match:
			route, params = match
			print ("MATCHED", route, params)
		else:
			print ("No match")

# EOF
