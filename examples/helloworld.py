"""
Basic Hello World Example

This demonstrates the simplest possible Extra web service.
Features shown:
- Basic service class
- Path parameter capture with {any}
- Request counting with instance state
- Plain text responses
- Extra logging for nicer output

Usage:
    python helloworld.py

Test with:
    curl http://localhost:8000/anything
    curl http://localhost:8000/hello
"""

from extra import Service, HTTPRequest, HTTPResponse, on, run
from extra.utils.logging import info


class HelloWorld(Service):
	def __init__(self):
		super().__init__()
		self.count: int = 0

	@on(GET="{any}")
	def hello_world(self, request: HTTPRequest, any: str) -> HTTPResponse:
		"""Responds with Hello World message and increments counter."""
		self.count += 1
		info(f"Hello World request #{self.count}", Path=f"/{any}", Peer=request.peer)
		return request.respond(
			f"Hello, World! #{self.count} (path: /{any})", "text/plain"
		)


if __name__ == "__main__":
	info("Starting Hello World service")
	info("Test commands:")
	info("  curl http://localhost:8000/anything")
	info("  curl http://localhost:8000/hello")
	run(HelloWorld())

# EOF
