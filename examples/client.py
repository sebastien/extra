import asyncio
from extra.client import HTTPClient, pooling
from extra.utils.logging import info
from extra.utils.uri import URI


# NOTE: Start "examples/sse.py"
async def main(path: str, host: str = "127.0.0.1", port: int = 8000, ssl: bool = False):
	info(f"Client connecting to {host}:{port}{path}")
	# NOTE: Connection pooling does not seem to be working
	with pooling(idle=3600):
		for _ in range(n := 5):
			info("Trying request", Count=n)
			async for atom in HTTPClient.Request(
				host=host,
				method="GET",
				port=port,
				path=path,
				timeout=10.0,
				streaming=False,
				# NOTE: If you se this to False and you get pooling,
				# you'll get a Connection lost, which is expected.
				keepalive=_ < n - 1,
				ssl=ssl,
			):
				info(f"Received atom: {atom}")
			await asyncio.sleep(0.25)


if __name__ == "__main__":
	import sys

	uri = URI.Parse(sys.argv[1] if len(sys.argv) > 1 else "https://google.com/")
	print(
		asyncio.run(
			main(
				path=uri.path,
				host=uri.host,
				port=uri.port,
				ssl=uri.ssl,
			)
		)
	)
# EOF
