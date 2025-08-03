"""
CORS (Cross-Origin Resource Sharing) Example

This demonstrates handling CORS for cross-origin web requests.
Features shown:
- CORS headers configuration
- Pre-flight OPTIONS request handling
- Cross-origin API endpoints
- Manual CORS header setting
- Extra logging for nicer output

Usage:
    python cors.py

Test with:
    curl -H "Origin: https://example.com" http://localhost:8000/api/data
    curl -X OPTIONS -H "Origin: https://example.com" -H "Access-Control-Request-Method: POST" http://localhost:8000/api/data
"""

from extra import Service, HTTPRequest, HTTPResponse, on, expose, run
from extra.features.cors import setCORSHeaders
from extra.utils.logging import info


class CORSService(Service):
	PREFIX = "api/"

	@expose(GET="data")
	def get_data(self, request: HTTPRequest) -> HTTPResponse:
		"""API endpoint that returns data with CORS headers."""
		info(
			"CORS GET data request",
			Origin=request.getHeader("Origin"),
			Client=request.peer,
		)

		data = {
			"message": "This response includes CORS headers",
			"data": [1, 2, 3, 4, 5],
			"timestamp": "2024-01-01T00:00:00Z",
		}

		response = request.returns(data)
		return setCORSHeaders(response, allowAll=True)

	@on(POST="data")
	async def post_data(self, request: HTTPRequest) -> HTTPResponse:
		"""API endpoint that accepts POST data with CORS headers."""
		data = await request.body.load()
		origin = request.getHeader("Origin")

		info(
			"CORS POST data request",
			Origin=origin,
			Client=request.peer,
			DataSize=len(data) if data else 0,
		)

		response = request.returns(
			{"message": "Data received successfully", "received": data, "echo": True}
		)

		return setCORSHeaders(response, allowAll=True)

	@on(OPTIONS="{path:any}")
	def handle_preflight(self, request: HTTPRequest, path: str) -> HTTPResponse:
		"""Handle CORS preflight requests."""
		origin = request.getHeader("Origin")
		method = request.getHeader("Access-Control-Request-Method")

		info(
			"CORS preflight request",
			Path=path,
			Origin=origin,
			RequestedMethod=method,
			Client=request.peer,
		)

		response = request.respond("", "text/plain")
		return setCORSHeaders(response, origin=origin, allowAll=True)

	@expose(GET="info")
	def cors_info(self, request: HTTPRequest) -> HTTPResponse:
		"""Endpoint that explains CORS configuration."""
		info("CORS info requested", Client=request.peer)

		data = {
			"cors": {
				"enabled": True,
				"allow_all_origins": True,
				"allowed_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
				"allowed_headers": [
					"Content-Type",
					"Authorization",
					"X-Requested-With",
				],
			},
			"endpoints": {
				"GET /api/data": "Get data with CORS",
				"POST /api/data": "Post data with CORS",
				"OPTIONS /*": "Handle preflight requests",
			},
		}

		response = request.returns(data)
		return setCORSHeaders(response, allowAll=True)


if __name__ == "__main__":
	info("Starting CORS-enabled API service")
	info(
		"Test CORS with: curl -H 'Origin: https://example.com' http://localhost:8000/api/data"
	)
	run(CORSService())

# EOF
