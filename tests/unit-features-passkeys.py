import extra.features


failed = 0

if hasattr(extra.features, "passkeys"):
	print("FAIL: extra.features should not load passkeys by default")
	failed += 1

import extra.features.passkeys as passkeys

encoded = passkeys.bytesToBase64url(b"hello world")
decoded = passkeys.base64urlToBytes(encoded)
if decoded != b"hello world":
	print("FAIL: passkeys base64url helpers should round-trip bytes")
	failed += 1

if passkeys.available():
	try:
		passkeys.require()
	except RuntimeError:
		print("FAIL: passkeys.require should succeed when webauthn is available")
		failed += 1
else:
	try:
		passkeys.require()
		print("FAIL: passkeys.require should fail when webauthn is unavailable")
		failed += 1
	except RuntimeError:
		pass

	class DummyCredentials:
		def list(self):
			return []

		def get(self, credentialId: str):
			return None

		def create(self, data):
			pass

		def updateSignCount(self, credentialId: str, signCount: int):
			pass

	class DummyChallenges:
		def clean(self):
			pass

		def put(self, purpose: str, chal: str, **data):
			return {"purpose": purpose, "challenge": chal, **data}

		def take(self, purpose: str, chal: str, origin: str):
			return {"purpose": purpose, "challenge": chal, "origin": origin}

	service = passkeys.Passkeys(
		DummyCredentials(),
		DummyChallenges(),
		rpName="Example",
		rpIdForOrigin=lambda origin: "example.com",
	)
	try:
		service.registerOptions("https://example.com")
		print("FAIL: passkeys methods should fail when webauthn is unavailable")
		failed += 1
	except RuntimeError:
		pass

if failed:
	print(f"FAIL {failed} tests failed")
	print("ERR")
else:
	print("OK! All tests passed")
	print("EOK")


# EOF
