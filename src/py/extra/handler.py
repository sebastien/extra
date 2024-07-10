from typing import Any, Coroutine, Callable, cast
from base64 import b64encode, b64decode
from urllib.parse import urlparse, parse_qs
from functools import update_wrapper
import asyncio
from io import BytesIO
from .utils.io import asWritable
from .utils.logging import exception
from .model import Application, Service, mount
from .http.model import (
    HTTPRequest,
    HTTPRequestHeaders,
    HTTPResponseBlob,
    HTTPResponseFile,
    HTTPResponseStream,
    HTTPResponseAsyncStream,
    HTTPRequestBlob,
    HTTPResponse,
    headername,
)


# --
# ## Reference
#
# ### Event
#
# Common fields in the event object for web events:
#
# - `httpMethod`: The HTTP method used (GET, POST, PUT, DELETE, etc.).
# - `path`: The path of the request URL.
# - `headers`: A dictionary containing the request headers.
# - `queryStringParameters`: A dictionary containing the query string parameters (if any).
# - `pathParameters`: A dictionary containing the path parameters (if any) extracted from the request URL.
# - `body`: The request body (if any). This may be a string, a dictionary (for JSON payloads), or a base64-encoded string (for binary data).
# - `isBase64Encoded`: A boolean indicating whether the body is base64-encoded.
#
# Additional Fields with API Gateway Proxy Integration
#
# - `requestContext`: Contains additional metadata about the request, such as the request ID, stage, API ID, and more.
# - `resource`: The API Gateway resource path associated with the request.
# Context Object (context)
#
# The context object provides information about the Lambda function's execution environment and the invocation itself.
#
# ### Context Object
#
# - `functionName`: The name of the Lambda function.
# - `functionVersion`: The version of the function.
# - `invokedFunctionArn`: The Amazon Resource Name (ARN) of the function being invoked.
# - `memoryLimitInMB`: The memory limit allocated to the function.
# - `awsRequestId`: The unique ID assigned to this invocation of the Lambda function.
# - `logGroupName`: The name of the CloudWatch Logs group for the function.
# - `logStreamName`: The name of the CloudWatch Logs stream for the function.
# - `getRemainingTimeInMillis()`: A method to get the remaining execution time in milliseconds.
#
# ### Request Context
#
# This property provides valuable information about the context of the incoming
# request, helping you understand details about the API Gateway environment,
# authorization, and the client making the request. Here's what you'll
# typically find within `requestContext`:
#
# - `resourceId`: The ID of the API Gateway resource that triggered the Lambda function.
# - `apiId`: The ID of the API Gateway API.
# - `resourcePath`: The path of the API Gateway resource.
# - `httpMethod`: The HTTP method used in the request (GET, POST, etc.).
# - `accountId`: The AWS account ID associated with the API Gateway API.
# - `stage`: The deployment stage of the API Gateway API (e.g., 'dev', 'prod').
# - `requestId`: A unique identifier for the request.
# - `identity`: Information about the caller's identity:
# - `sourceIp`: The IP address of the client making the request.
# - `userAgent`: The user agent string of the client's browser or application.
# - `cognitoIdentityId`: (If applicable) The Cognito identity ID of the authenticated user.
# - `cognitoAuthenticationType`: (If applicable) The authentication type used by Cognito.
# - `authorizer`: (If applicable) Information from a custom authorizer (e.g., Lambda authorizer) that you've configured for your API Gateway API.


TAWSEvent = dict[str, str | bytes | int | float | bool | dict[str, str] | None]


class AWSLambdaEvent:
    @staticmethod
    def Create(
        method: str,
        uri: str,
        headers: dict[str, str] | None = None,
        body: str | bytes | None = None,
    ) -> TAWSEvent:
        """Creates an AWS Lambda API Gateway event from the given parameters."""
        url = urlparse(uri)
        params = {k: v[0] for k, v in parse_qs(url.query).items()}
        payload: TAWSEvent = {
            "httpMethod": method,
            "path": url.path,
            "queryStringParameters": params,
            "host": "localhost",
        }
        # FIXME: Not sure what the payload attribute is for.
        if body:
            # FIXME: Should be decode
            payload["payload"] = b64encode(body) if isinstance(body, bytes) else body
        if headers:
            payload["headers"] = headers
        return payload

    @staticmethod
    def AsRequest(event: dict) -> HTTPRequest:
        body: bytes = (
            (
                b64decode(event["body"].encode())
                if event.get("isBase64Encoded")
                else event["body"].encode()
            )
            if "body" in event
            else b""
        )
        raw_headers: dict[str, str] = {
            k.lower(): v
            for k, v in cast(dict[str, str], event.get("header", {})).items()
        }
        return HTTPRequest(
            method=event.get("httpMethod", "GET"),
            path=event.get("path", "/"),
            query=cast(dict[str, str], event.get("queryStringParameters", {})),
            headers=HTTPRequestHeaders(
                raw_headers,
                raw_headers.get("Content-Type"),
                int(raw_headers.get("Content-Length", len(body))),
            ),
            body=HTTPRequestBlob(body),
            # host=h.get("Host") or h.get("host") or "aws",
        )

    @staticmethod
    async def FromResponse(response: HTTPResponse) -> dict[str, Any]:
        """Returns an AWS Lambda event corresponding to the given response."""
        buffer = BytesIO()
        if response.body is None:
            pass
        elif isinstance(response.body, HTTPResponseBlob):
            buffer.write(response.body.payload or b"")
        elif isinstance(response.body, HTTPResponseFile):
            with open(response.body.path, "rb") as f:
                while data := f.read(32_000):
                    buffer.write(data)
        elif isinstance(response.body, HTTPResponseStream):
            # TODO: Should handle exception
            try:
                for chunk in response.body.stream:
                    buffer.write(asWritable(chunk))
            finally:
                response.body.stream.close()
        elif isinstance(response.body, HTTPResponseAsyncStream):
            # No keep alive with streaming as these are long
            # lived requests.
            try:
                async for chunk in response.body.stream:
                    buffer.write(asWritable(chunk))
            # TODO: Should handle exception
            finally:
                await response.body.stream.aclose()
        elif response.body is None:
            pass
        else:
            raise ValueError(f"Unsupported body format: {response.body}")
        size = buffer.tell()
        buffer.seek(0)
        # We force the content length
        response.setHeader("Content-Length", size)
        content_type = response.getHeader("Content-Type") or "text/plain"
        is_binary = (
            False
            if "text/" in content_type or content_type.startswith("application/json")
            else True
        )
        body = buffer.read(size)
        return {
            "statusCode": response.status,
            "headers": {headername(k): v for k, v in response.headers.items()},
            # FIXME: Ensure it's properly encoded
            "body": b64encode(body) if is_binary else body.decode("utf8"),
        }


class AWSLambdaHandler:

    def __init__(self, app: Application):
        self.app: Application = app

    async def handle(
        self, event: dict[str, Any], context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        req: HTTPRequest = AWSLambdaEvent.AsRequest(event)
        r: HTTPResponse | Coroutine[Any, HTTPResponse, Any] = self.app.process(req)
        if isinstance(r, HTTPResponse):
            res: HTTPResponse = r
        else:
            res = await r
        return await AWSLambdaEvent.FromResponse(res)


def request(event: dict[str, Any]) -> HTTPRequest:
    return AWSLambdaEvent.AsRequest(event)


async def aresponse(
    response: HTTPResponse | Coroutine[Any, HTTPResponse, Any]
) -> dict[str, Any]:
    if isinstance(response, HTTPResponse):
        res: HTTPResponse = response
    else:
        res = await response
    return await AWSLambdaEvent.FromResponse(res)


def response(
    response: HTTPResponse | Coroutine[Any, HTTPResponse, Any]
) -> dict[str, Any]:
    return asyncio.run(aresponse(response))


def handler(
    *components: Application | Service,
) -> AWSLambdaHandler:
    """Returns an AWS Lambda Handler function"""
    app = mount(*components)
    return AWSLambdaHandler(app)


def event(
    method: str,
    uri: str,
    headers: dict[str, str] | None = None,
    body: str | bytes | None = None,
) -> dict:
    return AWSLambdaEvent.Create(method=method, uri=uri, headers=headers, body=body)


def awslambda(
    handler: Callable[[HTTPRequest], HTTPResponse | Coroutine[Any, HTTPResponse, Any]]
):
    def wrapper(event: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        # TODO: Supports looking at pre/post, etc, registered in the `wrapper`.
        try:
            req = request(event)
        except Exception as e:
            exception(e, "Failed to parse AWS Lambda event")
            raise e from e
        try:
            res = handler(req)
        except Exception as e:
            exception(e, "Failed to handle AWS Lambda event")
            raise e from e
        return response(res)

    return update_wrapper(wrapper, handler)


# EOF
