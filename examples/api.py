"""
JSON API Example

This demonstrates building a JSON API with Extra framework.
Features shown:
- Service with PREFIX for mounting under /api/
- @expose decorator for automatic JSON encoding
- Route parameters with type conversion
- Service initialization with init()
- Mixed sync/async handlers
- Request body parsing
- Extra logging for nicer output

Usage:
    python api.py

Test with:
    curl http://localhost:8000/api/time
    curl http://localhost:8000/api/counter
    curl http://localhost:8000/api/counter/add/5
    curl -X POST http://localhost:8000/api/pong -H "Content-Type: application/json" -d '{"name":"John","age":30}'
"""

from extra import Service, HTTPRequest, HTTPResponse, on, expose, run
from extra.utils.logging import info
import time


class API(Service):
	PREFIX = "api/"

	def init(self):
		"""Initialize service state - called once when service starts."""
		self.count = 0
		info("API service initialized", Counter=self.count)

	@expose(GET="time")
	def time(self):
		"""Returns the current Unix timestamp."""
		info("Time endpoint requested")
		return {"timestamp": time.time(), "readable": time.ctime()}

	@expose(GET="counter")
	async def counter(self):
		"""Returns the current counter value."""
		info("Counter value requested", Value=self.count)
		return {"counter": self.count}

	@expose(GET="counter/add/{amount:int}")
	async def increment(self, amount: int):
		"""Increments the counter by the specified amount."""
		old_count = self.count
		self.count += amount
		info("Counter incremented", From=old_count, To=self.count, Amount=amount)
		return {"counter": self.count, "added": amount}

	@on(GET_POST="pong")
	async def pong(self, request: HTTPRequest) -> HTTPResponse:
		"""Echoes the request data back as JSON."""
		data = await request.body.load()
		info(
			"Pong request received",
			Method=request.method,
			DataSize=len(data) if data else 0,
		)
		return request.returns(
			{
				"method": request.method,
				"received": data,
				"headers": dict(request.headers),
			}
		)


if __name__ == "__main__":
	info("Starting JSON API service")
	info("Test commands:")
	info("  curl http://localhost:8000/api/time")
	info("  curl http://localhost:8000/api/counter")
	info("  curl http://localhost:8000/api/counter/add/5")
	info(
		'  curl -X POST http://localhost:8000/api/pong -H \'Content-Type: application/json\' -d \'{"name":"John","age":30}\''
	)
	run(API())

# EOF
