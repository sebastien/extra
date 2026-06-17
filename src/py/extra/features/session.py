from __future__ import annotations

import time
import secrets
from typing import Any, Callable, Protocol

from ..http.model import HTTPRequest, HTTPResponse


class SessionBackend(Protocol):
	def get(self, token: str) -> dict[str, Any] | None: ...
	def set(self, token: str, data: dict[str, Any]) -> None: ...
	def delete(self, token: str) -> None: ...


class MemorySessionBackend:
	def __init__(self) -> None:
		self.sessions: dict[str, dict[str, Any]] = {}

	def get(self, token: str) -> dict[str, Any] | None:
		return self.sessions.get(token)

	def set(self, token: str, data: dict[str, Any]) -> None:
		self.sessions[token] = data

	def delete(self, token: str) -> None:
		self.sessions.pop(token, None)


class SessionStore:
	def __init__(self, backend: SessionBackend | None = None, *, ttl: int = 86400 * 30) -> None:
		self.backend = backend or MemorySessionBackend()
		self.ttl = ttl

	def create(self, data: dict[str, Any]) -> str:
		token = secrets.token_urlsafe(48)
		self.backend.set(token, {**data, "createdAt": int(time.time())})
		return token

	def get(self, token: str | None) -> dict[str, Any] | None:
		if not token:
			return None
		return self.backend.get(token)

	def drop(self, token: str | None) -> None:
		if token:
			self.backend.delete(token)


def load(
	store: SessionStore,
	*,
	cookie: str = "session",
) -> Callable[[HTTPRequest, dict[str, Any]], HTTPResponse | None]:
	def transform(request: HTTPRequest, _params: dict[str, Any]) -> HTTPResponse | None:
		value = request.cookie(cookie)
		token = value.value if value else None
		request.sessionToken = token
		request.session = store.get(token)
		return None

	return transform


def session(
	store: SessionStore,
	*,
	cookie: str = "session",
	path: str = "/",
	httpOnly: bool = True,
	sameSite: str = "Lax",
	secure: bool | None = None,
	domain: str | None = None,
) -> Callable[[HTTPRequest, HTTPResponse], HTTPResponse]:
	def transform(request: HTTPRequest, response: HTTPResponse) -> HTTPResponse:
		if request.sessionData is not None:
			request.sessionToken = store.create(request.sessionData)
			request.session = request.sessionData
		if request.sessionToken is not None:
			response.setCookie(
				cookie,
				request.sessionToken,
				path=path,
				domain=domain,
				httpOnly=httpOnly,
				secure=secure,
				sameSite=sameSite,
				maxAge=store.ttl,
			)
		if request.clearSession:
			store.drop(request.sessionToken)
			response.clearCookie(
				cookie,
				path=path,
				domain=domain,
				httpOnly=httpOnly,
				secure=secure,
				sameSite=sameSite,
			)
		return response

	return transform


# EOF
