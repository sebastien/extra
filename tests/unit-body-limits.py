import asyncio

from extra.http.model import (
	HTTPBodyLimitError,
	HTTPBodyReader,
	HTTPHeaders,
	HTTPRequest,
)


class FakeBodyReader(HTTPBodyReader):
	def __init__(self, chunks: list[bytes]):
		super().__init__()
		self.chunks = chunks

	async def _read(
		self, timeout: float | None = None, size: int | None = None
	) -> bytes | None:
		if not self.chunks:
			return None
		chunk = self.chunks.pop(0)
		if size is None or len(chunk) <= size:
			return chunk
		head = chunk[:size]
		tail = chunk[size:]
		self.chunks.insert(0, tail)
		return head


async def testLimitExceeded() -> None:
	reader = FakeBodyReader([b"hello", b" world"])
	reader.setLimit(8)
	try:
		await reader.load()
		assert False, "Expected HTTPBodyLimitError"
	except HTTPBodyLimitError as e:
		assert e.limit == 8
		assert e.read > 8


async def testRequestSpool() -> None:
	reader = FakeBodyReader([b"a" * 1200])
	req = HTTPRequest(
		"POST", "/upload", None, HTTPHeaders({"Content-Length": "1200"}, None, 1200)
	)
	req._reader = reader
	f = await req.spool(maxSize=128)
	try:
		f.seek(0, 2)
		assert f.tell() == 1200
		assert bool(getattr(f, "_rolled", False))
	finally:
		f.close()


async def main() -> None:
	await testLimitExceeded()
	await testRequestSpool()


if __name__ == "__main__":
	asyncio.run(main())


# EOF
