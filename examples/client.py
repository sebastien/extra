import asyncio
from extra.client import HTTPClient, pooling
from extra.utils.logging import info
from extra.utils.uri import URI

"""
HTTP Client Example

This demonstrates the Extra HTTP client with connection pooling.
Features shown:
- HTTP client with connection pooling
- URI parsing for flexible URL input
- Keepalive connections
- SSL/TLS support
- Request iteration and response handling

Usage:
    python client.py [URL]
    python client.py https://httpbin.org/get
    python client.py http://localhost:8000/api/time

Default: https://google.com/
"""


async def make_requests(url_str: str, num_requests: int = 3):
	"""Make multiple HTTP requests to demonstrate connection pooling."""
	uri = URI.Parse(url_str)
	info(
		"Starting HTTP client demo",
		URL=url_str,
		Host=uri.host,
		Port=uri.port,
		SSL=uri.ssl,
		Requests=num_requests,
	)

	# Connection pooling keeps connections alive between requests
	with pooling(idle=3600):  # Keep connections for 1 hour
		for i in range(num_requests):
			info("Making request", Number=f"{i + 1}/{num_requests}")

			async for atom in HTTPClient.Request(
				host=uri.host,
				method="GET",
				port=uri.port,
				path=uri.path or "/",
				timeout=10.0,
				streaming=False,
				# Keep connection alive for all but last request
				keepalive=i < num_requests - 1,
				ssl=uri.ssl,
			):
				atom_type = type(atom).__name__
				if hasattr(atom, "status"):
					info("Response received", Type=atom_type, Status=atom.status)
				elif hasattr(atom, "payload"):
					# Truncate long responses for readability
					payload_size = len(atom.payload)
					preview = atom.payload[:100] if payload_size > 100 else atom.payload
					info(
						"Response data",
						Type=atom_type,
						Size=payload_size,
						Preview=str(preview),
					)
				else:
					info("Response atom", Type=atom_type)

			# Small delay between requests
			if i < num_requests - 1:
				await asyncio.sleep(0.5)

	info("HTTP client demo completed")


if __name__ == "__main__":
	import sys

	url = sys.argv[1] if len(sys.argv) > 1 else "https://httpbin.org/get"
	info("HTTP Client Example starting", DefaultURL="https://httpbin.org/get")
	info("Test commands:")
	info("  python client.py")
	info("  python client.py https://httpbin.org/get")
	info("  python client.py http://localhost:8000/api/time")
	asyncio.run(make_requests(url))

# EOF
