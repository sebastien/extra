from __future__ import annotations

import asyncio
import json

from extra.decorators import Expose
from extra.http.model import HTTPBodyBlob, HTTPHeaders, HTTPRequest
from extra.routing import Handler


failed = 0


def fail(message: str) -> None:
	global failed
	print(f"FAIL: {message}")
	failed += 1


async def bindJson(email: str = "", password: str = "", user: str = "") -> dict:
	return {"email": email, "password": password, "user": user}


async def bindForm(email: str = "", resetCode: str = "") -> dict:
	return {"email": email, "resetCode": resetCode}


def syncBind(email: str = "") -> dict:
	return {"email": email}


def bindOrigin(origin: str | None = None, user: str = "") -> dict:
	return {"origin": origin, "user": user}


async def decode(response) -> dict:
	payload = await response.body.load() if response.body else b""
	return json.loads(payload.decode())


json_body = b'{"email":"body@example.com","password":"secret","user":"body"}'
json_request = HTTPRequest(
	method="POST",
	path="/auth/alice",
	query={"email": "query@example.com"},
	headers=HTTPHeaders(
		{"Content-Type": "application/json", "Content-Length": str(len(json_body))},
		"application/json",
		len(json_body),
	),
	body=HTTPBodyBlob.FromBytes(json_body),
)
json_handler = Handler(
	bindJson,
	methods=[("POST", "/auth/{user}")],
	expose=Expose(data=True),
)
json_response = asyncio.run(json_handler._callAsync(json_request, {"user": "alice"}))
json_data = asyncio.run(decode(json_response))
if json_data != {
	"email": "body@example.com",
	"password": "secret",
	"user": "alice",
}:
	fail("@expose(data=True) should bind JSON data and preserve route params")


form_body = b"email=form%40example.com&resetCode=abc123"
form_request = HTTPRequest(
	method="POST",
	path="/auth/reset",
	query=None,
	headers=HTTPHeaders(
		{
			"Content-Type": "application/x-www-form-urlencoded",
			"Content-Length": str(len(form_body)),
		},
		"application/x-www-form-urlencoded",
		len(form_body),
	),
	body=HTTPBodyBlob.FromBytes(form_body),
)
form_handler = Handler(
	bindForm,
	methods=[("POST", "/auth/reset")],
	expose=Expose(data=True),
)
form_response = asyncio.run(form_handler._callAsync(form_request, {}))
form_data = asyncio.run(decode(form_response))
if form_data != {"email": "form@example.com", "resetCode": "abc123"}:
	fail("@expose(data=True) should bind form data")


sync_handler = Handler(syncBind, methods=[("POST", "/auth")], expose=Expose(data=True))
try:
	sync_handler._callSync(json_request, {})
	fail("@expose(data=True) should reject sync handlers")
except RuntimeError as error:
	if "requires an async handler" not in str(error):
		fail("sync expose(data=True) should raise the expected error")


origin_request = HTTPRequest(
	method="POST",
	path="/auth/alice",
	query=None,
	headers=HTTPHeaders({"Origin": "https://example.com"}),
	body=HTTPBodyBlob.FromBytes(b""),
)
origin_request.origin = "https://example.com"
origin_handler = Handler(
	bindOrigin,
	methods=[("POST", "/auth/{user}")],
	expose=Expose(origin=True),
)
origin_response = origin_handler._callSync(origin_request, {"user": "alice"})
origin_data = asyncio.run(decode(origin_response))
if origin_data != {"origin": "https://example.com", "user": "alice"}:
	fail("@expose(origin=True) should bind request origin and preserve route params")


if failed:
	print(f"FAIL {failed} tests failed")
	print("ERR")
else:
	print("OK! All tests passed")
	print("EOK")


# EOF
