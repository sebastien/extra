import asyncio
from extra.client import HTTPClient
from extra.http.model import HTTPBodyBlob
from extra.utils.codec import GZipDecoder


# --
# ## HTTP Client Example
#
# Shows how to use the HTTP client module, in this case with GZipped content.
# Note how the client API by default returns an iterator, which may be more
# low-level than what you'd be used to (with
async def main(path: str, host: str = "127.0.0.1", port: int = 443, ssl: bool = True):
	transform = GZipDecoder()

	with open("/dev/stdout", "wb") as f:
		async for atom in HTTPClient.Request(
			host=host,
			method="GET",
			port=port,
			path=path,
			timeout=11.0,
			streaming=False,
			headers={"Accept-Encoding": "gzip"},
			ssl=ssl,
		):
			if isinstance(atom, HTTPBodyBlob):
				f.write(transform.feed(atom.payload) or b"")
		f.write(transform.flush() or b"")


if __name__ == "__main__":
	import sys

	args = sys.argv[2:] or ["/index"]
	n = len(args)
	# Test: curl -v https://cdn.statically.io/gh/lodash/lodash/4.17.15-npm/lodash.min.js
	asyncio.run(
		main(
			path="/gh/lodash/lodash/4.17.15-npm/lodash.min.js",
			host="cdn.statically.io",
		)
	)
# EOF
