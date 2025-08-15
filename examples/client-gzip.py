"""
HTTP Client with GZip Decompression Example

This demonstrates HTTP client with automatic GZip decompression.
Features shown:
- HTTP client with compression support
- GZip decoder for compressed responses
- Binary data handling
- SSL/HTTPS connections

Usage:
    python client-gzip.py

This example fetches a compressed JavaScript file and decompresses it.
"""

import asyncio
from extra.client import HTTPClient
from extra.http.model import HTTPBodyBlob
from extra.utils.codec import GZipDecoder
from extra.utils.logging import info


async def fetch_compressed(host: str, path: str, port: int = 443, ssl: bool = True):
	"""Fetch and decompress a GZip-encoded HTTP response."""
	info("Starting GZip fetch", Host=host, Path=path, Port=port, SSL=ssl)

	# Initialize GZip decoder
	decoder = GZipDecoder()
	total_compressed = 0
	total_decompressed = 0

	try:
		async for atom in HTTPClient.Request(
			host=host,
			method="GET",
			port=port,
			path=path,
			timeout=15.0,
			streaming=False,
			headers={"Accept-Encoding": "gzip"},
			ssl=ssl,
		):
			if isinstance(atom, HTTPBodyBlob):
				# Track compressed size
				chunk_size = len(atom.payload)
				total_compressed += chunk_size

				# Decompress the data
				decompressed = decoder.feed(atom.payload)
				if decompressed:
					decompressed_size = len(decompressed)
					total_decompressed += decompressed_size
					# Preview for demo (first 200 chars)
					preview = decompressed[:200].decode("utf-8", errors="ignore")
					info(
						"Decompressed chunk",
						CompressedSize=chunk_size,
						DecompressedSize=decompressed_size,
						Preview=f"{preview}...",
					)

			elif hasattr(atom, "status"):
				info("HTTP response", Status=atom.status)
			elif hasattr(atom, "headers"):
				encoding = atom.headers.get("content-encoding", "none")
				info("Response headers", ContentEncoding=encoding)

		# Flush any remaining data
		final_data = decoder.flush()
		if final_data:
			total_decompressed += len(final_data)
			preview = final_data[:200].decode("utf-8", errors="ignore")
			info(
				"Final decompressed chunk",
				Size=len(final_data),
				Preview=f"{preview}...",
			)

		compression_ratio = (
			round((total_compressed / total_decompressed) * 100, 1)
			if total_decompressed > 0
			else 0
		)
		info(
			"Decompression complete",
			CompressedBytes=total_compressed,
			DecompressedBytes=total_decompressed,
			CompressionRatio=f"{compression_ratio}%",
		)

	except Exception as e:
		info("GZip client error", Error=str(e))


if __name__ == "__main__":
	info("Starting GZip HTTP client example")
	info("Test: Fetches compressed JavaScript from CDN and decompresses it")
	info("URL: https://cdn.statically.io/gh/lodash/lodash/4.17.15-npm/lodash.min.js")
	# Example: Fetch a compressed JavaScript library
	asyncio.run(
		fetch_compressed(
			host="cdn.statically.io", path="/gh/lodash/lodash/4.17.15-npm/lodash.min.js"
		)
	)

# EOF
