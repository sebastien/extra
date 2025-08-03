"""
Request Capture Example

This demonstrates capturing and inspecting HTTP requests.
Features shown:
- Catch-all routes with {path:any}
- Streaming request body reading
- Request header inspection
- Support for both GET and POST
- Extra logging for nicer output

Usage:
    python capture.py

Test with:
    curl http://localhost:8000/anything
    curl -X POST -H "Content-Type: application/json" -d '{"key":"value"}' http://localhost:8000/data
    curl -X POST -d "form data" http://localhost:8000/form
"""

from extra import Service, HTTPRequest, HTTPResponse, on, run
from extra.utils.logging import info


class CaptureService(Service):
	@on(GET_POST="/{path:any}")
	async def capture_request(self, request: HTTPRequest, path: str) -> HTTPResponse:
		"""Captures and returns details about any HTTP request."""

		# Option 1: Read body in one shot
		# body = await request.body.load()

		# Option 2: Read body incrementally (demonstrated here)
		chunks: list[bytes] = []
		async for chunk in request.read():
			if chunk is None:
				break
			chunks.append(chunk)

		body_bytes = b"".join(chunks)

		# Try to decode body as text
		try:
			body_text = body_bytes.decode("utf-8")
		except UnicodeDecodeError:
			body_text = f"<binary data: {len(body_bytes)} bytes>"

		# Log captured request details
		info(
			"Request captured",
			Method=request.method,
			Path=f"/{path}",
			Peer=request.peer,
			BodySize=len(body_bytes),
			ContentType=request.getHeader("Content-Type") or "none",
		)

		return request.returns(
			{
				"captured": {
					"method": request.method,
					"path": f"/{path}",
					"query": dict(request.query) if hasattr(request, "query") else {},
					"headers": dict(request.headers),
					"body": body_text,
					"body_size": len(body_bytes),
				}
			}
		)


if __name__ == "__main__":
	info("Starting request capture service")
	info("Test commands:")
	info("  curl http://localhost:8000/anything")
	info(
		"  curl -X POST -H 'Content-Type: application/json' -d '{\"key\":\"value\"}' http://localhost:8000/data"
	)
	info("  curl -X POST -d 'form data' http://localhost:8000/form")
	run(CaptureService())

# EOF
