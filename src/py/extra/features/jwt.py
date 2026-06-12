# Module: jwt
# JSON Web Token (JWT) serialization, parsing, and signing.

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets

from .tokens import Token, decode, encode


def b64url(data: bytes) -> str:
	"""Encodes `data` into a URL-safe Base64 string with no padding."""
	return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def unb64url(data: str) -> bytes:
	"""Decodes a URL-safe Base64 string `data` back to bytes."""
	padding = "=" * (-len(data) % 4)
	return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def unhex(secret: str) -> bytes:
	"""Converts a hexadecimal string `secret` to bytes."""
	return bytes.fromhex(secret)


def hmac256(input: str, secret: str) -> bytes:
	"""Generates an HMAC-SHA256 signature of `input` using `secret`."""
	return hmac.new(unhex(secret), input.encode("utf8"), hashlib.sha256).digest()


def sign(token: Token, secret: str) -> str:
	"""Serializes and signs `token` into a JWT string using `secret`."""
	header = {"alg": "HS256", "typ": "JWT"}
	payload = {"payload": encode(token)}
	encodedHeader = b64url(json.dumps(header, separators=(",", ":")).encode("utf8"))
	encodedPayload = b64url(json.dumps(payload, separators=(",", ":")).encode("utf8"))
	signingInput = f"{encodedHeader}.{encodedPayload}"
	signature = b64url(hmac256(signingInput, secret))
	return f"{signingInput}.{signature}"


def parse(token: str, secret: str) -> Token | None:
	"""Parses and validates a JWT string `token` using `secret`, returning the decoded Token or None."""
	try:
		encodedHeader, encodedPayload, encodedSignature = token.split(".")
		signingInput = f"{encodedHeader}.{encodedPayload}"
		expected = hmac256(signingInput, secret)
		actual = unb64url(encodedSignature)
		if not hmac.compare_digest(actual, expected):
			return None
		payload = json.loads(unb64url(encodedPayload).decode("utf8"))
		encoded = payload.get("payload")
		return decode(encoded) if isinstance(encoded, str) else None
	except Exception:
		return None


def key() -> str:
	"""Generates a random 32-byte hexadecimal signing key."""
	return secrets.token_hex(32)


# EOF
