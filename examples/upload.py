"""
File Upload Example

This demonstrates handling file uploads with HTML forms.
Features shown:
- HTML form serving with @expose
- File upload handling via POST
- Request body parsing
- Mixed content types (HTML and JSON responses)
- Extra logging for nicer output

Usage:
    python upload.py

Test with:
    # Via browser: http://localhost:8000/
    # Via curl:
    curl -F "file=@example.txt" -F "description=Test file" http://localhost:8000/upload
"""
# EXPECT: Starting file upload service
# EXPECT: Visit http://localhost:8000 to access the upload form

from extra import Service, HTTPRequest, HTTPResponse, on, expose, run
from extra.utils.logging import info


class UploadService(Service):
	@expose(GET=("/", "/index"), contentType="text/html", raw=True)
	def index(self, request: HTTPRequest) -> str:
		"""Serves a simple file upload form."""
		info("Upload form requested", Client=request.peer)
		return """
		<!DOCTYPE html>
		<html>
		<head>
			<title>File Upload Example</title>
		</head>
		<body>
			<h1>File Upload Demo</h1>
			<form action="/upload" method="POST" enctype="multipart/form-data">
				<div>
					<label for="file">Choose file:</label>
					<input type="file" id="file" name="file" required>
				</div>
				<div>
					<label for="description">Description:</label>
					<input type="text" id="description" name="description" placeholder="Optional description">
				</div>
				<div>
					<button type="submit">Upload File</button>
				</div>
			</form>
		</body>
		</html>
		"""

	@on(POST="/upload")
	async def upload(self, request: HTTPRequest) -> HTTPResponse:
		"""Handles file upload and returns upload statistics."""
		try:
			# Spool body to memory/disk for safer large upload handling.
			body_file = await request.spool(maxSize=1_000_000)
			body_file.seek(0, 2)
			body_size = body_file.tell()
			body_file.seek(0)
			body_preview_bytes = body_file.read(100)
			content_type = request.headers.get("content-type", "")

			info(
				"File upload received",
				Client=request.peer,
				ContentType=content_type,
				BodySize=body_size,
			)

			# Basic upload processing
			upload_info = {
				"status": "success",
				"content_type": content_type,
				"body_size": body_size,
				"body_preview": str(body_preview_bytes) + "..."
				if body_size > 100
				else str(body_preview_bytes),
			}

			# In a real application, you would:
			# 1. Parse multipart form data properly
			# 2. Save files to disk with proper names
			# 3. Validate file types and sizes
			# 4. Handle multiple files

			return request.returns(upload_info)

		except Exception as e:
			info("Upload error", Error=str(e), Client=request.peer)
			return request.returns({"status": "error", "message": str(e)})


if __name__ == "__main__":
	info("Starting file upload service")
	info("Visit http://localhost:8000 to access the upload form")
	info("Test commands:")
	info(
		"  curl -F 'file=@example.txt' -F 'description=Test file' http://localhost:8000/upload"
	)
	run(UploadService())

# EOF
