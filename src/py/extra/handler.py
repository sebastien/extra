from typing import Any, Coroutine, cast
from base64 import b64encode, b64decode
from urllib.parse import urlparse, parse_qs
from io import BytesIO
from .utils.io import asWritable
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
)


class AWSLambdaEvent:
    @staticmethod
    def Create(
        method: str,
        uri: str,
        headers: dict[str, str] | None = None,
        body: str | bytes | None = None,
    ) -> dict:
        """Creates an AWS Lambda API Gateway event from the given parameters."""
        url = urlparse(uri)
        params = {k: v[0] for k, v in parse_qs(url.query).items()}
        payload = {
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
                raw_headers.get("content-type"),
                int(raw_headers.get("content-length", len(body))),
            ),
            body=HTTPRequestBlob(body),
            # host=h.get("Host") or h.get("host") or "aws",
        )


class AWSLambdaHandler:

    def __init__(self, app: Application):
        self.app: Application = app

    async def handle(
        self, event: dict[str, Any], context: dict[str, Any] | None = None
    ):
        req: HTTPRequest = AWSLambdaEvent.AsRequest(event)
        r: HTTPResponse | Coroutine[Any, HTTPResponse, Any] = self.app.process(req)
        if isinstance(r, HTTPResponse):
            res = r
        else:
            res = await r

        buffer = BytesIO()
        if res.body is None:
            pass
        elif isinstance(res.body, HTTPResponseBlob):
            buffer.write(res.body.payload or b"")
        elif isinstance(res.body, HTTPResponseFile):
            with open(res.body.path, "rb") as f:
                while data := f.read(32_000):
                    buffer.write(data)
        elif isinstance(res.body, HTTPResponseStream):
            # TODO: Should handle exception
            try:
                for chunk in res.body.stream:
                    buffer.write(asWritable(chunk))
            finally:
                res.body.stream.close()
        elif isinstance(res.body, HTTPResponseAsyncStream):
            # No keep alive with streaming as these are long
            # lived requests.
            try:
                async for chunk in res.body.stream:
                    buffer.write(asWritable(chunk))
            # TODO: Should handle exception
            finally:
                await res.body.stream.aclose()
        elif res.body is None:
            pass
        else:
            raise ValueError(f"Unsupported body format: {res.body}")
        size = buffer.tell()
        buffer.seek(0)
        # We force the content length
        res.setHeader("content-length", size)
        content_type = res.getHeader("content-type") or "text/plain"
        is_binary = (
            False
            if "text/" in content_type or content_type.startswith("application/json")
            else True
        )
        body = buffer.read(size)
        return {
            "statusCode": res.status,
            "headers": res.headers,
            # FIXME: Ensure it's properly encoded
            "body": b64encode(body) if is_binary else body.decode("utf8"),
        }


def handler(
    *components: Application | Service,
) -> AWSLambdaHandler:
    app = mount(*components)
    return AWSLambdaHandler(app)


# EOF
