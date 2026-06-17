# Module: tokens
# Token representation, serialization, and deserialization using a compact custom codec.

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import json
from typing import cast

from .capabilities import Action, Capability, Constraint, Scope, ConstraintArg
from .capabilities import capability, constraint, scope

Actions: dict[str, str] = {
	"Create": "C",
	"Update": "U",
	"Write": "W",
	"Set": "S",
	"Add": "A",
	"Delete": "D",
	"Describe": "d",
	"Read": "r",
	"List": "l",
	"Search": "s",
	"Execute": "x",
}

Constraints: dict[str, str] = {
	"Expires": "e",
	"Throttle": "t",
	"Quota": "q",
}


@dataclass(slots=True)
class Token:
	"""Represents a capability-based security token containing subject scope, capabilities, and constraints."""

	subject: Scope
	capabilities: list[Capability] = field(default_factory=list)
	constraints: list[Constraint] = field(default_factory=list)


def token(
	subject: Scope,
	capabilities: list[Capability] | None = None,
	constraints: list[Constraint] | None = None,
) -> Token:
	"""Factory function that creates a `Token` with `subject`, `capabilities`, and `constraints`."""
	return Token(
		subject=subject,
		capabilities=[] if capabilities is None else capabilities,
		constraints=[] if constraints is None else constraints,
	)


def mapping(encode: dict[str, str]) -> dict[str, dict[str, str]]:
	"""Builds a two-way mapping dictionary from an encoding dictionary `encode`."""
	decode: dict[str, str] = {}
	for key, value in encode.items():
		decode[value] = key
	return {"encode": encode, "decode": decode}


def _b64_encode(data: bytes) -> str:
	return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64_decode(data: str) -> bytes:
	padding = "=" * (-len(data) % 4)
	return base64.urlsafe_b64decode((data + padding).encode("ascii"))


class TokenCodec:
	"""Codec for encoding and decoding capability tokens to and from a compact string format."""

	def __init__(
		self,
		actions: dict[str, str] | None = None,
		constraints: dict[str, str] | None = None,
	):
		"""Initializes the codec with mapping tables for `actions` and `constraints`."""
		self.actions = mapping(Actions if actions is None else actions)
		self.constraints = mapping(Constraints if constraints is None else constraints)

	def encodeToken(self, token: Token) -> str:
		"""Encodes `token` into its compact string representation."""
		return "|".join(
			[
				self.encodeScope(token.subject),
				",".join(self.encodeCapability(item) for item in token.capabilities),
				",".join(self.encodeConstraint(item) for item in token.constraints),
			]
		)

	def encodeScope(self, value: Scope) -> str:
		"""Encodes a `value` Scope into a string path."""
		parts: list[str] = []
		for item in value:
			if isinstance(item, str):
				parts.append(item)
			elif item.wildcard:
				parts.append(item.wildcard)
			elif item.variable:
				parts.append(
					f"{item.prefix}{{{item.variable}}}"
					if item.prefix
					else f"{{{item.variable}}}"
				)
			else:
				parts.append(str(item))
		return "/".join(parts)

	def encodeScopes(self, scopes: list[Scope]) -> str:
		"""Encodes a list of `scopes` into a single string joined by plus signs."""
		return "+".join(self.encodeScope(item) for item in scopes) if scopes else ""

	def encodeAction(self, value: Action) -> str:
		"""Encodes a single action `value` using the configured action map."""
		return self.actions["encode"].get(value, value)

	def encodeActions(self, actions: list[Action]) -> str:
		"""Encodes a list of `actions` into a single string joined by ampersands."""
		return "&".join(self.encodeAction(item) for item in actions) if actions else ""

	def encodeCapability(self, value: Capability) -> str:
		"""Encodes a single `value` Capability into a colon-separated string representation."""
		return (
			f"{self.encodeScopes(value.subject or [])}:"
			f"{self.encodeActions(value.actions)}:"
			f"{self.encodeScopes(value.object)}:"
			f"{','.join(self.encodeConstraint(item) for item in (value.where or []))}"
		)

	def encodeConstraint(self, value: Constraint) -> str:
		"""Encodes a single `value` Constraint with its arguments serialized as Base64 JSON."""
		name = self.constraints["encode"].get(value.op, value.op)
		payload = json.dumps(value.args, separators=(",", ":")).encode("utf8")
		return f"{name}({_b64_encode(payload)})"

	def decodeToken(self, encodedToken: str) -> Token:
		"""Decodes an `encodedToken` string back into a Token instance."""
		parts = encodedToken.split("|")
		encodedSubject = parts[0] if parts else ""
		encodedCapabilities = parts[1] if len(parts) > 1 else ""
		encodedConstraints = parts[2] if len(parts) > 2 else ""
		return token(
			self.decodeScope(encodedSubject),
			[
				self.decodeCapability(item)
				for item in encodedCapabilities.split(",")
				if item
			],
			[
				self.decodeConstraint(item)
				for item in encodedConstraints.split(",")
				if item
			],
		)

	def decodeScope(self, encodedScope: str) -> Scope:
		"""Decodes an `encodedScope` string back into a Scope."""
		return scope(encodedScope) if encodedScope else []

	def decodeAction(self, encodedAction: str) -> str:
		"""Decodes a single action string `encodedAction` using the mapping table."""
		return self.actions["decode"].get(encodedAction, encodedAction)

	def decodeScopes(self, encodedScopes: str) -> list[Scope]:
		"""Decodes an `encodedScopes` string of multiple scopes separated by plus signs."""
		res: list[Scope] = []
		for item in encodedScopes.split("+"):
			decoded = self.decodeScope(item)
			if decoded:
				res.append(decoded)
		return res

	def decodeCapability(self, encodedCapability: str) -> Capability:
		"""Decodes an `encodedCapability` string back into a Capability."""
		encodedSubjects, encodedActions, encodedObjects, encodedConstraints = (
			encodedCapability.split(":", 3) + ["", "", "", ""]
		)[:4]
		constraints = [
			self.decodeConstraint(item)
			for item in encodedConstraints.split(",")
			if item
		]
		return capability(
			self.decodeScopes(encodedSubjects),
			[self.decodeAction(item) for item in encodedActions.split("&") if item],
			self.decodeScopes(encodedObjects),
			*constraints,
		)

	def decodeConstraint(self, encodedConstraint: str) -> Constraint:
		"""Decodes an `encodedConstraint` string back into a Constraint."""
		i = encodedConstraint.index("(")
		code = encodedConstraint[:i]
		name = self.constraints["decode"].get(code, code)
		payload = encodedConstraint[i + 1 : -1]
		args = cast(list[object], json.loads(_b64_decode(payload).decode("utf8")))
		return constraint(name, *cast(tuple[ConstraintArg, ...], tuple(args)))


codec = TokenCodec()


def encode(value: Token) -> str:
	"""Encodes the `value` Token into its compact string representation using the default codec."""
	return codec.encodeToken(value)


def decode(encoded: str) -> Token:
	"""Decodes an `encoded` token string back into a Token instance using the default codec."""
	return codec.decodeToken(encoded)


# EOF
