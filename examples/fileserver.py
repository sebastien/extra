"""
Static File Server Example

This demonstrates serving static files from the filesystem.
Features shown:
- Built-in FileService for static file serving
- Automatic MIME type detection
- Directory browsing capabilities
- Extra logging for nicer output

Usage:
    python fileserver.py

Test with:
    http://localhost:8000/           # Browse current directory
    http://localhost:8000/README.md  # Serve specific file

The server will serve files from the current working directory.
"""

from extra import run
from extra.services.files import FileService
from extra.utils.logging import info


class StaticFileServer(FileService):
	"""
	A static file server that serves files from the current directory.

	FileService provides:
	- Automatic MIME type detection
	- Directory listing
	- Range request support for large files
	- Security checks to prevent directory traversal
	"""

	def __init__(self):
		super().__init__()
		info("Static file server initialized")
		# You can customize the file service here:
		# - Set custom root directory
		# - Configure allowed file types
		# - Set up caching headers
		# - Add custom error pages


if __name__ == "__main__":
	info("Starting static file server")
	info("Serving files from current working directory")
	info("Access examples: http://localhost:8000/README.md")
	run(StaticFileServer())

# EOF
