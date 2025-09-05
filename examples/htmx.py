"""
HTMX Web Application Example

This demonstrates building interactive web applications with HTMX.
Features shown:
- HTML template generation with extra.utils.htmpl
- HTMX integration for dynamic content
- Server-side rendering with state management
- Interactive counter with HTMX
- Extra logging for nicer output

Usage:
    python htmx.py

Test with:
    http://localhost:8000/         # Main page with counter
    http://localhost:8000/counter  # HTMX endpoint for counter updates
"""

from extra import Service, HTTPRequest, HTTPResponse, on, expose, run
from extra.utils.htmpl import Node, H
from extra.utils.logging import info


class HTMXApp(Service):
	def __init__(self):
		super().__init__()
		self.counter = 0
		info("HTMX application initialized", Counter=self.counter)

	def html_page(self, *body_content: Node) -> str:
		"""Creates a complete HTML page with HTMX included."""
		page = H.html(
			H.head(
				H.title("HTMX Example"),
				H.script(src="https://unpkg.com/htmx.org@1.9.12"),
				H.style(
					"""
					body { font-family: Arial, sans-serif; padding: 20px; }
					.counter { font-size: 24px; margin: 10px 0; }
					button { padding: 10px 20px; margin: 5px; cursor: pointer; }
				"""
				),
			),
			H.body(*body_content),
		)
		return str(page)

	@on(GET="/")
	def index(self, request: HTTPRequest) -> HTTPResponse:
		"""Main page with interactive counter."""
		info(
			"HTMX main page requested", Client=request.peer, CurrentCounter=self.counter
		)

		content = [
			H.h1("HTMX Counter Example"),
			H.div(
				H.div(f"Count: {self.counter}", id="counter", class_="counter"),
				H.button(
					"Increment",
					**{
						"hx-post": "/counter/increment",
						"hx-target": "#counter",
						"hx-swap": "innerHTML",
					},
				),
				H.button(
					"Decrement",
					**{
						"hx-post": "/counter/decrement",
						"hx-target": "#counter",
						"hx-swap": "innerHTML",
					},
				),
				H.button(
					"Reset",
					**{
						"hx-post": "/counter/reset",
						"hx-target": "#counter",
						"hx-swap": "innerHTML",
					},
				),
			),
			H.p("Click the buttons to see HTMX in action!"),
		]

		return request.respond(self.html_page(*content), "text/html")

	@on(POST="/counter/increment")
	def increment(self, request: HTTPRequest) -> HTTPResponse:
		"""HTMX endpoint to increment counter."""
		old_value = self.counter
		self.counter += 1
		info(
			"Counter incremented", From=old_value, To=self.counter, Client=request.peer
		)
		return request.respond(f"Count: {self.counter}", "text/html")

	@on(POST="/counter/decrement")
	def decrement(self, request: HTTPRequest) -> HTTPResponse:
		"""HTMX endpoint to decrement counter."""
		old_value = self.counter
		self.counter -= 1
		info(
			"Counter decremented", From=old_value, To=self.counter, Client=request.peer
		)
		return request.respond(f"Count: {self.counter}", "text/html")

	@on(POST="/counter/reset")
	def reset(self, request: HTTPRequest) -> HTTPResponse:
		"""HTMX endpoint to reset counter."""
		old_value = self.counter
		self.counter = 0
		info("Counter reset", From=old_value, To=self.counter, Client=request.peer)
		return request.respond(f"Count: {self.counter}", "text/html")


if __name__ == "__main__":
	info("Starting HTMX web application")
	info("Visit http://localhost:8000 for interactive counter demo")
	run(HTMXApp())

# EOF
