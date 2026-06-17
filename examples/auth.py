"""
Authentication and capability example

This demonstrates the new security helpers:
- Capability definitions and scope matching
- Token minting with the compact codec
- JWT signing and parsing
- Bearer token request authentication
- Request query/body loading with loadParams()

Usage:
    python auth.py

Test with:
    curl 'http://localhost:8000/mint?user=alice'
    curl -H 'Authorization: Bearer <token>' http://localhost:8000/profile/alice
"""
# EXPECT: Starting authentication example
# EXPECT: Test commands:

from extra import HTTPRequest, HTTPResponse, Service, expose, run
from extra.features.auth import bearerTokenAuth, parseTokenJwt, signTokenJwt
from extra.features.capabilities import CapabilityMatcher, capability, scope, where
from extra.features.jwt import key
from extra.features.tokens import TokenCodec, encode, token
from extra.utils.logging import info
import time


class Auth(Service):
	def init(self):
		"""Initializes the signing key and auth helpers."""
		self.secret = key()
		self.codec = TokenCodec()
		self.auth = bearerTokenAuth(self.secret)
		self.matcher = CapabilityMatcher()
		info("Auth example initialized")
		info("Use /mint?user=alice to mint a token")

	@expose(GET="mint")
	async def mint(self, request: HTTPRequest) -> dict:
		"""Mints a JWT bearer token for the requested user."""
		params = await request.loadParams()
		user = str(params.get("user", "alice"))
		ttl = int(params.get("ttl", 3600))
		cap = capability(
			f"/user/{user}",
			["Read"],
			f"/profile/{user}",
			where.Expires(time.time() + ttl),
		)
		value = token(scope(f"/user/{user}"), [cap], [])
		signed = signTokenJwt(value, self.secret)
		parsed = parseTokenJwt(signed, self.secret)
		info("Minted token", User=user, Token=encode(value))
		return {
			"user": user,
			"ttl": ttl,
			"compact": encode(value),
			"jwt": signed,
			"roundtrip": parsed is not None,
			"authorization": f"Bearer {signed}",
		}

	@expose(GET="profile/{user}")
	async def profile(self, request: HTTPRequest, user: str) -> HTTPResponse:
		"""Validates the bearer token and returns the requested profile."""
		auth = self.auth.resolve(request)
		if auth is None:
			return request.returns({"error": "missing_or_invalid_token"}, status=401)

		allowed = self.matcher.match(
			self.codec.encodeScope(auth.subject),
			"Read",
			f"/profile/{user}",
			*auth.capabilities,
		)
		if allowed is not True:
			return request.returns({"error": "forbidden"}, status=403)

		return request.returns(
			{
				"user": user,
				"subject": self.codec.encodeScope(auth.subject),
				"token": encode(auth),
			},
		)


if __name__ == "__main__":
	info("Starting authentication example")
	info("Test commands:")
	info("  curl 'http://localhost:8000/mint?user=alice'")
	info(
		"  curl -H 'Authorization: Bearer <token>' http://localhost:8000/profile/alice"
	)
	run(Auth())

# EOF
