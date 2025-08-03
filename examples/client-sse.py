"""
HTTP Client Server-Sent Events Example

This demonstrates consuming Server-Sent Events with the Extra HTTP client.
Features shown:
- Streaming HTTP client (streaming=True)
- SSE event consumption
- Real-time data processing

Usage:
    # First, start the SSE server:
    python sse.py

    # Then run this client:
    python client-sse.py

Test different endpoints:
    # Modify the path in main() to test:
    # /time      - Default 1 second interval
    # /time/5    - 5 second interval
"""

import asyncio
from extra.client import HTTPClient
from extra.utils.logging import info


async def consume_sse(host: str = "localhost", port: int = 8000, path: str = "/time/2"):
	"""Connect to SSE endpoint and process events in real-time."""
	info("Connecting to SSE stream", Host=host, Port=port, Path=path)

	try:
		async for atom in HTTPClient.Request(
			method="GET",
			host=host,
			port=port,
			path=path,
			timeout=30.0,  # Longer timeout for streaming
			streaming=True,  # Enable streaming mode for SSE
			ssl=False,
		):
			atom_type = type(atom).__name__

			# Process different types of response atoms
			if hasattr(atom, "payload"):
				payload = (
					atom.payload.decode("utf-8")
					if isinstance(atom.payload, bytes)
					else str(atom.payload)
				)
				info("SSE content received", Type=atom_type, Content=payload.strip())
			elif hasattr(atom, "status"):
				info("HTTP response", Type=atom_type, Status=atom.status)
			else:
				info("SSE atom received", Type=atom_type, Data=str(atom))

	except Exception as e:
		info("SSE client error", Error=str(e))


if __name__ == "__main__":
	info("Starting SSE client example")
	info("Prerequisites: Start SSE server with 'python examples/sse.py'")
	asyncio.run(consume_sse())

# EOF
