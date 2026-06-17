# Module: auth
# HTTP bearer token authentication and JWT-based security integration.

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import hmac
import secrets
import time
from typing import Any

from ..model import Service
from ..http.model import HTTPRequest
from .capabilities import CapabilityMatcher, ConstraintRuntime, scope
from .jwt import parse, sign
from .session import SessionStore, load, session
from .tokens import Token


def _expires(expiresAt: int | float) -> bool:
	return bool(expiresAt > time.time())


def _matchesScope(pattern: str, value: str) -> bool:
	return CapabilityMatcher().matchScope(scope(pattern), value) is not None


defaultConstraintRuntime: ConstraintRuntime = {
	"Expires": _expires,
	"MatchesScope": _matchesScope,
}


@dataclass(slots=True)
class ScryptPasswords:
	n: int = 16384
	r: int = 8
	p: int = 1
	dklen: int = 64
	saltBytes: int = 16

	def hash(self, password: str) -> str:
		salt = secrets.token_hex(self.saltBytes)
		key = hashlib.scrypt(
			password.encode(),
			salt=salt.encode(),
			n=self.n,
			r=self.r,
			p=self.p,
			dklen=self.dklen,
		)
		return f"{salt}${base64.b64encode(key).decode()}"

	def verify(self, password: str, stored: str) -> bool:
		salt, keyB64 = stored.split("$", 1)
		key = hashlib.scrypt(
			password.encode(),
			salt=salt.encode(),
			n=self.n,
			r=self.r,
			p=self.p,
			dklen=self.dklen,
		)
		return hmac.compare_digest(base64.b64encode(key).decode(), keyB64)


passwords = ScryptPasswords()


class SessionAuthService(Service):
	COOKIE = "session"
	SESSION_TTL = 86400 * 30

	def __init__(
		self,
		store: SessionStore | None = None,
		*,
		cookie: str | None = None,
		prefix: str | None = None,
	):
		super().__init__(prefix=prefix)
		self.cookie = cookie or self.COOKIE
		self.sessions = store or SessionStore(ttl=self.SESSION_TTL)
		type(self).PRE = (load(self.sessions, cookie=self.cookie),)
		type(self).POST = (session(self.sessions, cookie=self.cookie),)

	def login(self, request: HTTPRequest, data: dict[str, Any]) -> None:
		request.sessionData = data

	def logout(self, request: HTTPRequest) -> None:
		request.clearSession = True

	def current(self, request: HTTPRequest) -> dict[str, Any] | None:
		return request.session


def signTokenJwt(token: Token, secret: str) -> str:
	"""Signs the given `token` into a JWT string using `secret`."""
	return sign(token, secret)


def parseTokenJwt(encoded: str, secret: str) -> Token | None:
	"""Parses and validates the JWT string `encoded` using `secret`, returning the decoded Token or None if invalid."""
	return parse(encoded, secret)


@dataclass(slots=True)
class BearerTokenAuth:
	"""Middleware helper that extracts and validates bearer tokens from requests."""

	secret: str

	def resolve(self, request: HTTPRequest) -> Token | None:
		"""Resolves the authorization token from the HTTP headers of `request`."""
		header = request.getHeader("Authorization") or request.getHeader(
			"authorization"
		)
		if not header or not header.startswith("Bearer "):
			return None
		return parse(header[7:].strip(), self.secret)


def bearerTokenAuth(
	secret: str,
) -> BearerTokenAuth:
	"""Factory that creates a `BearerTokenAuth` instance with `secret`."""
	return BearerTokenAuth(secret=secret)


# EOF
