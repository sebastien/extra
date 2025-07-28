import asyncio
from extra.client import HTTPClient
from extra.utils.logging import info


# --
# ## HTTP Client Sever Set Eevents
#
# This shows how to use the HTTP client with the `streaming=True` option
# to process SSE responses.
#
# This should be run with the `examples/sse.py` as the server.


# NOTE: Start "examples/sse.py"
async def main(host: str = "localhost", port=8003):
	info("Connecting", Host=host, Port=port)
	async for atom in HTTPClient.Request(
		method="GET",
		host=host,
		port=port,
		path="/time/5",
		timeout=10.0,
		streaming=True,
		ssl=False,
	):
		info(f"Received atom: {atom}")


info("Make sure you have an SSE server running, eg: 'python examples/sse.py")
print(asyncio.run(main()))
# EOF
