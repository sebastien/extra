"""
Filesystem Watch SSE Example

This demonstrates real-time file change streaming with Server-Sent Events
and browser auto-reload with `watch.js`.
Features shown:
- Cross-platform watcher backend selection (Linux/macOS)
- Low-level CLI watcher integration (no Python watcher dependency)
- SSE stream for file changes
- Auto-reload script generation from query params
- Small HTML page that subscribes and reloads on change

Usage:
    python watch.py

Test with:
    curl http://localhost:8000/watch
    curl http://localhost:8000/watch/src
    open http://localhost:8000/
"""
# EXPECT: Starting filesystem watch service

from extra import HTTPRequest, HTTPResponse, on, run
from extra.services.watch import FileWatchService
from extra.utils.logging import info


class WatchDemo(FileWatchService):
	@on(GET="/")
	def index(self, request: HTTPRequest) -> HTTPResponse:
		return request.respondHTML(
			"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Watch Demo</title>
    <style>
      :root { font-family: sans-serif; line-height: 1.4; }
      body { max-width: 720px; margin: 2rem auto; padding: 0 1rem; }
      code { background: #f2f2f2; padding: 0.1rem 0.3rem; border-radius: 4px; }
      pre { background: #f8f8f8; padding: 0.9rem; border-radius: 8px; overflow: auto; }
    </style>
  </head>
  <body>
    <h1>Filesystem Watch + Auto Reload</h1>
    <p>
      This page auto reloads when files change in <code>src/py</code> or
      <code>tests</code>.
    </p>
    <p>Try editing a Python file in one of those folders and save.</p>
    <pre>&lt;script src="/watch.js?src/py&amp;tests&amp;window=0.2&amp;debounce=180"&gt;&lt;/script&gt;</pre>

    <script src="/watch.js?src/py&tests&window=0.2&debounce=180"></script>
  </body>
</html>
"""
		)


if __name__ == "__main__":
	info("Starting filesystem watch service")
	info("Watching current directory by default")
	info("Try: curl http://localhost:8000/watch")
	info("Demo page: http://localhost:8000/")
	info("Browser auto-reload helper: <script src='/watch.js?src/py&tests'></script>")
	run(WatchDemo())

# EOF
