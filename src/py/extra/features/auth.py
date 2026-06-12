# Module: auth
# HTTP bearer token authentication and JWT-based security integration.

from __future__ import annotations

from dataclasses import dataclass
import time

from ..http.model import HTTPRequest
from .capabilities import CapabilityMatcher, ConstraintRuntime, scope
from .jwt import parse, sign
from .tokens import Token

def _expires(expiresAt: int | float) -> bool:
	return bool(expiresAt > time.time())


def _matchesScope(pattern: str, value: str) -> bool:
	return CapabilityMatcher().matchScope(scope(pattern), value) is not None


defaultConstraintRuntime: ConstraintRuntime = {
	"Expires": _expires,
	"MatchesScope": _matchesScope,
}


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
