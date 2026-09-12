import gzip
import tempfile
from pathlib import Path

from extra.handler import AWSLambdaEvent
from extra.services.files import FileService


def makeRequest(method: str, headers: dict[str, str] | None = None):
	return AWSLambdaEvent.AsRequest(
		AWSLambdaEvent.Create(method, "/app.js", headers=headers)
	)


with tempfile.TemporaryDirectory(prefix="extra-files-gzip-") as tmp:
	root = Path(tmp)
	payload = b"console.log('compressed');\n"
	(root / "app.js.gz").write_bytes(gzip.compress(payload))
	service = FileService(root=root, enableCORS=False)

	response = service.read(makeRequest("GET", {"Accept-Encoding": "gzip"}), "app.js")
	assert response.status == 200
	assert response.getHeader("Content-Type") == "text/javascript"
	assert response.getHeader("Content-Encoding") == "gzip"
	assert response.getHeader("Vary") == "Accept-Encoding"
	assert response.body is not None
	assert response.body.path.read_bytes() == (root / "app.js.gz").read_bytes()

	head = service.head(makeRequest("HEAD", {"Accept-Encoding": "gzip"}), "app.js")
	assert head.status == 200
	assert head.getHeader("Content-Encoding") == "gzip"
	assert head.body is None

	not_accepted = service.read(makeRequest("GET"), "app.js")
	assert not_accepted.status != 200

# EOF
