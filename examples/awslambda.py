"""
AWS Lambda Handler Example

This demonstrates how to expose Extra request handlers as AWS Lambda
entrypoints using `extra.handler.awslambda`.

Features shown:
- Non-streaming Lambda handler
- Streaming-style Lambda handler (generator response)
- Dispatcher-based Lambda handler with service routes
- Local event creation with `extra.handler.event`

Note:
    In this adapter, streamed responses are fully collected before returning
    the Lambda payload, so the final Lambda `body` is a single string.

Usage:
    # Non-streaming handler
    #   Handler: examples.awslambda.lambda_non_streaming_handler
    # Streaming example handler
    #   Handler: examples.awslambda.lambda_streaming_handler
    # Dispatcher-based handler (async)
    #   Handler: examples.awslambda.lambda_dispatcher_handler

Local demo:
    python awslambda.py
"""
# EXPECT: Non-streaming response:
# EXPECT: Streaming response:
# EXPECT: Dispatcher /hello response:
# EXPECT: Dispatcher /stream response:

from typing import Iterator, Any
import json

from extra import Service, HTTPRequest, HTTPResponse, on
from extra.handler import awslambda, event, awshandler


def non_streaming(request: HTTPRequest) -> HTTPResponse:
	"""Simple JSON response for standard Lambda/API Gateway calls."""
	return request.returns(
		{
			"mode": "non-streaming",
			"method": request.method,
			"path": request.path,
			"query": dict(request.query),
		}
	)


def streaming(request: HTTPRequest) -> HTTPResponse:
	"""Generator-based response to demonstrate streaming-style handlers."""

	def body() -> Iterator[str]:
		yield "chunk-1\n"
		yield "chunk-2\n"
		yield "chunk-3\n"

	return request.respond(body(), contentType="text/plain")


class RoutedLambda(Service):
	"""Service mounted in an app so Lambda requests go through dispatcher."""

	@on(GET="hello")
	def hello(self, request: HTTPRequest) -> HTTPResponse:
		return request.returns(
			{
				"mode": "dispatcher",
				"route": "/hello",
				"method": request.method,
				"path": request.path,
				"query": dict(request.query),
			}
		)

	@on(GET="stream")
	def stream(self, request: HTTPRequest) -> HTTPResponse:
		def body() -> Iterator[str]:
			yield "dispatcher-chunk-1\n"
			yield "dispatcher-chunk-2\n"

		return request.respond(body(), contentType="text/plain")


lambda_non_streaming_handler = awslambda(non_streaming)
lambda_streaming_handler = awslambda(streaming)
lambda_dispatcher_handler = awshandler(RoutedLambda())


if __name__ == "__main__":
	non_streaming_event = event("GET", "/hello?name=lambda")
	non_streaming_result: dict[str, Any] = lambda_non_streaming_handler(
		non_streaming_event, None
	)
	print("Non-streaming response:")
	print(json.dumps(non_streaming_result, indent=2))

	streaming_event = event("GET", "/stream")
	streaming_result: dict[str, Any] = lambda_streaming_handler(streaming_event, None)
	print("\nStreaming response:")
	print(json.dumps(streaming_result, indent=2))

	dispatcher_hello_event = event("GET", "/hello?name=lambda")
	dispatcher_hello_result: dict[str, Any] = lambda_dispatcher_handler(
		dispatcher_hello_event, None
	)
	print("\nDispatcher /hello response:")
	print(json.dumps(dispatcher_hello_result, indent=2))

	dispatcher_stream_event = event("GET", "/stream")
	dispatcher_stream_result: dict[str, Any] = lambda_dispatcher_handler(
		dispatcher_stream_event, None
	)
	print("\nDispatcher /stream response:")
	print(json.dumps(dispatcher_stream_result, indent=2))

# EOF
