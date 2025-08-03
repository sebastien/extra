"""
Server-Sent Events (SSE) Example

This demonstrates real-time streaming with Server-Sent Events.
Features shown:
- SSE event streaming with proper format
- Route parameters with type conversion
- Async generators for streaming responses
- Client disconnect handling
- Both SSE and chunked transfer encoding

Usage:
    python sse.py

Test with:
    curl http://localhost:8000/time
    curl http://localhost:8000/time/2  # 2 second delay
    curl http://localhost:8000/chunks
"""

from extra import Service, on, run
from extra.utils.logging import info
from typing import AsyncIterator
import time
import asyncio


class SSE(Service):
	@on(GET="/time")
	@on(GET="/time/{delay:int}")
	def time(self, request, delay: float | int = 1) -> AsyncIterator[str]:
		"""Streams current time every `delay` seconds via Server-Sent Events."""

		async def stream():
			counter = 0
			max_events = 10

			info(
				"Starting SSE time stream",
				Delay=delay,
				MaxEvents=max_events,
				Client=request.peer,
			)
			while counter < max_events:
				info(
					"SSE event sent",
					Event=f"{counter + 1}/{max_events}",
					Timestamp=time.time(),
				)

				# SSE format: event line, data line, blank line
				yield "event: time\n"
				yield f"data: {{'timestamp': {time.time()}, 'counter': {counter + 1}, 'readable': '{time.ctime()}'}}\n\n"

				await asyncio.sleep(delay)
				counter += 1

			# Send completion event
			info("SSE stream completing")
			yield "event: complete\n"
			yield "data: Stream finished\n\n"

		return request.onClose(lambda _: info("SSE stream stopped by client")).respond(
			stream(), contentType="text/event-stream"
		)

	@on(GET="/chunks")
	def chunks(self, request) -> AsyncIterator[str]:
		"""Demonstrates chunked transfer encoding with JSON array."""
		info("Starting chunked JSON stream", Client=request.peer)

		def stream():
			yield "["
			for i in range(10):
				if i > 0:
					yield ","
				yield f"{{'item': {i}, 'value': {i * i}}}"
			yield "]"

		return request.respond(
			stream(),
			contentType="application/json",
		)


if __name__ == "__main__":
	info("Starting Server-Sent Events service")
	info("Test commands:")
	info("  curl http://localhost:8000/time")
	info("  curl http://localhost:8000/time/2")
	info("  curl http://localhost:8000/chunks")
	run(SSE())

# EOF
