"""
Middleware and Decorators Example

This demonstrates middleware functionality using pre/post decorators.
Features shown:
- @pre decorator for request preprocessing
- @post decorator for response modification
- Request/response logging middleware
- Authentication middleware simulation
- Error handling middleware

Usage:
    python middleware.py

Test with:
    curl http://localhost:8000/public
    curl -H "Authorization: Bearer valid-token" http://localhost:8000/protected
    curl -H "Authorization: Bearer invalid-token" http://localhost:8000/protected
    curl http://localhost:8000/error
"""

from extra import Service, HTTPRequest, HTTPResponse, on, expose, run
from extra.decorators import pre, post
from extra.utils.logging import info
import time


# Middleware functions
@pre
def request_logger(request: HTTPRequest) -> HTTPRequest:
	"""Log incoming requests."""
	info(
		"Request received",
		Method=request.method,
		Path=request.path,
		Client=request.peer,
	)
	# Add start time for response time calculation
	request.start_time = time.time()
	return request


@pre
def auth_middleware(request: HTTPRequest) -> HTTPRequest:
	"""Check authorization for protected routes."""
	if request.path.startswith("/protected"):
		auth_header = request.getHeader("Authorization")
		if not auth_header or not auth_header.startswith("Bearer "):
			raise ValueError("Missing or invalid Authorization header")

		token = auth_header[7:]  # Remove 'Bearer ' prefix
		if token != "valid-token":
			raise ValueError("Invalid token")

		info("Authentication successful", Token="valid", Path=request.path)
		# Add user info to request
		request.user = {"id": 123, "name": "John Doe"}

	return request


@post
def response_logger(request: HTTPRequest, response: HTTPResponse) -> HTTPResponse:
	"""Log response details and add performance headers."""
	duration = time.time() - getattr(request, "start_time", time.time())

	info(
		"Response sent",
		Status=response.status,
		Path=request.path,
		Duration=f"{duration:.3f}s",
	)

	# Add response time header
	response.setHeader("X-Response-Time", f"{duration:.3f}s")
	response.setHeader("X-Server", "Extra-Framework")

	return response


@post
def security_headers(request: HTTPRequest, response: HTTPResponse) -> HTTPResponse:
	"""Add security headers to all responses."""
	response.setHeader("X-Content-Type-Options", "nosniff")
	response.setHeader("X-Frame-Options", "DENY")
	response.setHeader("X-XSS-Protection", "1; mode=block")
	return response


class MiddlewareService(Service):
	@expose(GET="public")
	@request_logger
	@response_logger
	@security_headers
	def public_endpoint(self) -> dict:
		"""Public endpoint with logging middleware."""
		return {
			"message": "This is a public endpoint",
			"middleware": ["request_logger", "response_logger", "security_headers"],
			"protected": False,
		}

	@expose(GET="protected")
	@request_logger
	@auth_middleware
	@response_logger
	@security_headers
	def protected_endpoint(self, request: HTTPRequest) -> dict:
		"""Protected endpoint requiring authentication."""
		user = getattr(request, "user", None)
		return {
			"message": "This is a protected endpoint",
			"user": user,
			"middleware": [
				"request_logger",
				"auth_middleware",
				"response_logger",
				"security_headers",
			],
			"protected": True,
		}

	@on(GET="error")
	@request_logger
	@response_logger
	@security_headers
	def error_endpoint(self, request: HTTPRequest) -> HTTPResponse:
		"""Endpoint that demonstrates error handling."""
		try:
			# Simulate an error
			raise RuntimeError("Simulated error for testing")
		except Exception as e:
			info("Error occurred in endpoint", Error=str(e), Path=request.path)
			return request.returns(
				{"error": True, "message": str(e), "type": type(e).__name__}, status=500
			)

	@expose(GET="middleware-info")
	def middleware_info(self) -> dict:
		"""Information about available middleware."""
		return {
			"available_middleware": {
				"request_logger": "Logs incoming requests with timing",
				"auth_middleware": "Validates Bearer token authentication",
				"response_logger": "Logs responses with performance metrics",
				"security_headers": "Adds security headers to responses",
			},
			"endpoints": {
				"/public": "Public endpoint with basic middleware",
				"/protected": "Protected endpoint requiring Bearer token",
				"/error": "Demonstrates error handling in middleware",
				"/middleware-info": "This information endpoint",
			},
			"test_token": "valid-token",
		}


if __name__ == "__main__":
	info("Starting middleware and decorators example")
	info("Test endpoints:")
	info("  curl http://localhost:8000/public")
	info(
		"  curl -H 'Authorization: Bearer valid-token' http://localhost:8000/protected"
	)
	info("  curl http://localhost:8000/middleware-info")
	run(MiddlewareService())

# EOF
