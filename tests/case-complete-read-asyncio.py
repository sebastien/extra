import asyncio
import hashlib
import time

# --
# A reference aysncio implementation which reads a complete request.

CHUNK_SIZE = 1024


def log(*message):
	print("[async] ", *(str(_) for _ in message))


async def handle_client(reader, writer):
	try:
		# Read the HTTP request headers
		headers = b""
		t = time.monotonic()
		while True:
			line = await reader.readline()
			if not line.strip():
				break
			headers += line

		# Find the Content-Length header
		content_length = 0
		for header_line in headers.split(b"\r\n"):
			if header_line.startswith(b"Content-Length:"):
				content_length = int(header_line.split(b":")[1].strip())

		# Read the request body in chunks
		sha256 = hashlib.sha256()
		iterations: int = 0
		bytes_read = 0
		while bytes_read < content_length:
			chunk_size = min(CHUNK_SIZE, content_length - bytes_read)
			chunk = await reader.read(chunk_size)
			if not chunk:
				break
			sha256.update(chunk)
			bytes_read += len(chunk)
			iterations += 1

		# Calculate the SHA-256 digest
		sha256_digest = sha256.hexdigest()

		elapsed = time.monotonic() - t
		log(f"--> Received: {sha256_digest} {bytes_read}")
		log(f"... Duration: {elapsed:0.2f} iterations={iterations}")
		# Send the response
		res = f"Read:{sha256_digest} {bytes_read}"
		response = f"HTTP/1.1 200 OK\r\nContent-Length: {len(res)}\r\n\r\n{res}"
		writer.write(response.encode())
		await writer.drain()

	except Exception as e:
		print(f"Error: {str(e)}")

	finally:
		writer.close()


async def main():
	server = await asyncio.start_server(handle_client, "localhost", 8000)

	async with server:
		await server.serve_forever()


if __name__ == "__main__":
	asyncio.run(main())

# EOF
