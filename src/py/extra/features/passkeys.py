from __future__ import annotations

import base64
from dataclasses import dataclass
import secrets
from typing import Any, Callable, Iterable, Protocol, cast


_WEBAUTHN_ERROR: ImportError | None = None

try:
	from webauthn import (  # type: ignore[import-not-found]
		generate_authentication_options,
		generate_registration_options,
		verify_authentication_response,
		verify_registration_response,
	)
	from webauthn.helpers.structs import (  # type: ignore[import-not-found]
		AuthenticatorSelectionCriteria,
		PublicKeyCredentialDescriptor,
		PublicKeyCredentialType,
		UserVerificationRequirement,
	)
except ImportError as error:
	_WEBAUTHN_ERROR = error


def available() -> bool:
	return _WEBAUTHN_ERROR is None


def require() -> None:
	if _WEBAUTHN_ERROR is not None:
		raise RuntimeError(
			"Passkeys require the optional 'webauthn' dependency. Install extra[passkeys]."
		) from _WEBAUTHN_ERROR


def bytesToBase64url(value: bytes) -> str:
	return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def base64urlToBytes(value: str) -> bytes:
	padding = "=" * (-len(value) % 4)
	return base64.urlsafe_b64decode((value + padding).encode("ascii"))


@dataclass(slots=True)
class PasskeyCredentialData:
	credentialId: str
	publicKey: str
	signCount: int
	userHandle: str


class PasskeyCredential(Protocol):
	credentialId: str
	publicKey: str
	signCount: int
	userHandle: str


class PasskeyCredentials(Protocol):
	def list(self) -> Iterable[PasskeyCredential]: ...
	def get(self, credentialId: str) -> PasskeyCredential | None: ...
	def create(self, data: PasskeyCredentialData) -> None: ...
	def updateSignCount(self, credentialId: str, signCount: int) -> None: ...


class PasskeyChallenges(Protocol):
	def clean(self) -> None: ...
	def put(self, purpose: str, chal: str, **data: object) -> dict[str, Any]: ...
	def take(self, purpose: str, chal: str, origin: str) -> dict[str, Any]: ...


class Passkeys:
	def __init__(
		self,
		credentials: PasskeyCredentials,
		challenges: PasskeyChallenges,
		*,
		rpName: str,
		rpIdForOrigin: Callable[[str | None], str | None],
		userName: str = "user",
		userDisplayName: str = "User",
	):
		self.credentials = credentials
		self.challenges = challenges
		self.rpName = rpName
		self.rpIdForOrigin = rpIdForOrigin
		self.userName = userName
		self.userDisplayName = userDisplayName

	def registerOptions(self, origin: str) -> dict[str, Any]:
		require()
		self.challenges.clean()
		rpId = self.rpIdForOrigin(origin)
		if not rpId:
			raise ValueError("Origin not allowed")
		userId = secrets.token_bytes(32)
		userHandle = bytesToBase64url(userId)
		options = generate_registration_options(
			rp_id=rpId,
			rp_name=self.rpName,
			user_name=self.userName,
			user_id=userId,
			user_display_name=self.userDisplayName,
			authenticator_selection=AuthenticatorSelectionCriteria(
				user_verification=UserVerificationRequirement.PREFERRED,
			),
		)
		chal = bytesToBase64url(options.challenge)
		self.challenges.put(
			"register",
			chal,
			origin=origin,
			rpId=rpId,
			userHandle=userHandle,
		)
		return {
			"publicKey": {
				"rp": {"name": options.rp.name, "id": options.rp.id},
				"user": {
					"id": bytesToBase64url(options.user.id),
					"name": options.user.name,
					"displayName": options.user.display_name,
				},
				"challenge": chal,
				"pubKeyCredParams": [
					{"type": "public-key", "alg": p.alg}
					for p in options.pub_key_cred_params
				],
				"timeout": options.timeout,
				"authenticatorSelection": {
					"authenticatorAttachment": "platform",
					"userVerification": "preferred",
					"residentKey": "preferred",
					"requireResidentKey": False,
				},
				"attestation": "none",
			},
			"userHandle": userHandle,
		}

	def register(
		self, credential: dict[str, Any], chal: str, origin: str
	) -> dict[str, str]:
		require()
		stored = self.challenges.take("register", chal, origin)
		verified = verify_registration_response(
			credential=credential,
			expected_challenge=base64urlToBytes(chal),
			expected_rp_id=stored["rpId"],
			expected_origin=origin,
			require_user_verification=False,
		)
		credId = bytesToBase64url(verified.credential_id)
		if not self.credentials.get(credId):
			self.credentials.create(
				PasskeyCredentialData(
					credentialId=credId,
					publicKey=bytesToBase64url(verified.credential_public_key),
					signCount=verified.sign_count,
					userHandle=cast(str, stored["userHandle"]),
				)
			)
		return {"credentialId": credId, "userHandle": cast(str, stored["userHandle"])}

	def loginOptions(self, origin: str) -> dict[str, Any]:
		require()
		self.challenges.clean()
		rpId = self.rpIdForOrigin(origin)
		if not rpId:
			raise ValueError("Origin not allowed")
		creds = list(self.credentials.list())
		if not creds:
			return {"publicKey": None, "message": "No credentials registered"}
		chalBytes = secrets.token_bytes(32)
		chal = bytesToBase64url(chalBytes)
		allow = [
			PublicKeyCredentialDescriptor(
				type=PublicKeyCredentialType.PUBLIC_KEY,
				id=base64urlToBytes(cred.credentialId),
			)
			for cred in creds
		]
		options = generate_authentication_options(
			rp_id=rpId,
			challenge=chalBytes,
			allow_credentials=allow,
			user_verification=UserVerificationRequirement.PREFERRED,
		)
		self.challenges.put("login", chal, origin=origin, rpId=rpId)
		return {
			"publicKey": {
				"challenge": chal,
				"timeout": options.timeout,
				"rpId": options.rp_id,
				"allowCredentials": [
					{"type": "public-key", "id": bytesToBase64url(cred.id)}
					for cred in allow
				],
				"userVerification": "preferred",
			},
		}

	def login(
		self, credential: dict[str, Any], chal: str, origin: str
	) -> dict[str, str]:
		require()
		stored = self.challenges.take("login", chal, origin)
		credId = credential.get("id", "")
		storedCred = self.credentials.get(credId)
		if not storedCred:
			raise ValueError("Credential not found")
		verified = verify_authentication_response(
			credential=credential,
			expected_challenge=base64urlToBytes(chal),
			expected_rp_id=stored["rpId"],
			expected_origin=origin,
			credential_public_key=base64urlToBytes(storedCred.publicKey),
			credential_current_sign_count=storedCred.signCount,
			require_user_verification=False,
		)
		self.credentials.updateSignCount(credId, verified.new_sign_count)
		return {"credentialId": credId, "userHandle": storedCred.userHandle}


# EOF
