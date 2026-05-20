import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from extra.handler import AWSLambdaEvent
from extra.http.model import HTTPBodyFile
from extra.services.files import FileService
from extra.server import AIOSocketBodyWriter


def makeRequest(method: str, headers: dict[str, str] | None = None):
	return AWSLambdaEvent.AsRequest(
		AWSLambdaEvent.Create(method, "/sample.txt", headers=headers)
	)


with TemporaryDirectory() as tmp:
	root = Path(tmp)
	path = root / "sample.txt"
	data = b"0123456789"
	path.write_bytes(data)

	request = makeRequest("GET", {"Range": "bytes=2-5"})
	response = request.respondFile(path, rangeHeader=request.header("Range"))
	assert response.status == 206
	assert response.getHeader("Accept-Ranges") == "bytes"
	assert response.getHeader("Content-Range") == "bytes 2-5/10"
	assert response.getHeader("Content-Length") == "4"
	assert isinstance(response.body, HTTPBodyFile)
	assert response.body.start == 2
	assert response.body.end == 5
	aws_response = asyncio.run(AWSLambdaEvent.FromResponse(response))
	assert aws_response["body"] == "2345"

	service = FileService(root)
	request = makeRequest("GET", {"Range": "bytes=4-7"})
	response = service.read(request, "sample.txt")
	assert response.status == 206
	assert response.getHeader("Content-Range") == "bytes 4-7/10"
	assert response.getHeader("Content-Length") == "4"
	assert isinstance(response.body, HTTPBodyFile)
	aws_response = asyncio.run(AWSLambdaEvent.FromResponse(response))
	assert aws_response["body"] == "4567"

	request = makeRequest("HEAD", {"Range": "bytes=1-3"})
	response = service.head(request, "sample.txt")
	assert response.status == 206
	assert response.body is None
	assert response.getHeader("Accept-Ranges") == "bytes"
	assert response.getHeader("Content-Range") == "bytes 1-3/10"
	assert response.getHeader("Content-Length") == "3"

	class FakeLoop:
		def __init__(self) -> None:
			self.calls: list[tuple[object, int, int | None]] = []
			self.data: bytearray = bytearray()

		async def sock_sendfile(
			self,
			client: object,
			file: object,
			offset: int = 0,
			count: int | None = None,
		) -> None:
			self.calls.append((client, offset, count))
			file.seek(offset)  # type: ignore[attr-defined]
			self.data.extend(file.read(count))  # type: ignore[attr-defined]

	loop = FakeLoop()
	writer = AIOSocketBodyWriter(object(), loop)
	asyncio.run(writer._writeFile(path, start=2, end=5))
	assert loop.calls == [(writer.client, 2, 4)]
	assert bytes(loop.data) == b"2345"

# EOF
