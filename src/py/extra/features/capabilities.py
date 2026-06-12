# Module: capabilities
# Security capabilities, scope matching, and runtime constraint evaluation.

from __future__ import annotations

from dataclasses import dataclass
from inspect import isawaitable
import re
from typing import Any, Awaitable, Callable, TypeAlias, cast

Primitive: TypeAlias = str | int | float | bool | None
Action: TypeAlias = str
ConstraintArg: TypeAlias = Primitive | list[Any] | dict[str, Any]
ConstraintPredicate: TypeAlias = Callable[..., bool | Awaitable[bool]]
ConstraintRuntime: TypeAlias = dict[str, ConstraintPredicate]
ScopeContext: TypeAlias = dict[str, str | int | float | bool | None]

_SCOPE_RE = re.compile(
	r"(?:(?P<prefix>[a-zA-Z0-9_-]+)?\{(?P<variable>[a-zA-Z0-9_]+)\}|(?P<wildcard>\*\*?))"
)
_CTX_RE = re.compile(r"^\$\{(?P<varname>[a-zA-Z0-9_]+)\}$")


@dataclass(slots=True, frozen=True)
class ScopeMatch:
	"""Compiled pattern match segment for a scope path."""

	prefix: str | None = None
	variable: str | None = None
	wildcard: str | None = None


Scope: TypeAlias = list[str | ScopeMatch]


@dataclass(slots=True)
class Constraint:
	"""Represents a dynamic constraint expression evaluated at runtime."""

	op: str
	args: list[ConstraintArg]


@dataclass(slots=True)
class Capability:
	"""Defines a permission granting actions on object scopes to subject scopes."""

	subject: list[Scope] | None
	object: list[Scope]
	actions: list[Action]
	where: list[Constraint] | None = None


class CapabilityMatcher:
	"""Evaluates and matches capabilities against subjects, actions, and objects."""

	def __init__(self, runtime: ConstraintRuntime | None = None):
		"""Initializes a matcher, optionally with a `runtime` of constraint predicates."""
		self.runtime: ConstraintRuntime = {} if runtime is None else runtime

	def match(
		self, subject: str, action: str, object: str, *capabilities: Capability
	) -> bool | Awaitable[bool]:
		"""Checks whether any of the `capabilities` permit the `subject` to perform `action` on the `object`."""
		ctx: dict[str, ConstraintArg] = {
			"subject": subject,
			"action": action,
			"object": object,
		}
		promises: list[Awaitable[bool]] = []
		for cap in capabilities:
			cap_ctx = dict(ctx)
			if cap.subject is not None:
				matched = self.matchScopes(cap.subject, subject, cap_ctx)
				if matched is None:
					continue
				cap_ctx.update(matched)
			if action not in cap.actions:
				continue
			matched_obj = self.matchScopes(cap.object, object, cap_ctx)
			if matched_obj is None:
				continue
			cap_ctx.update(matched_obj)
			result = self.matchConstraints(cap.where, cap_ctx) if cap.where else True
			if result is True:
				return True
			if result is False:
				continue
			promises.append(result)
		if promises:

			async def awaited() -> bool:
				for promise in promises:
					if await promise:
						return True
				return False

			return awaited()
		return False

	def matchScope(
		self,
		scope: Scope,
		path: str,
		context: ScopeContext | dict[str, ConstraintArg] | None = None,
	) -> ScopeContext | None:
		"""Matches a single `scope` pattern against the provided `path` using optional `context`."""
		res: ScopeContext = {}
		parts = [segment for segment in path.split("/") if segment]
		i = 0
		j = 0
		while i < len(scope) and j < len(parts):
			segment = parts[j]
			part = scope[i]
			if isinstance(part, str):
				if segment != part:
					return None
			else:
				if part.wildcard:
					if part.wildcard == "**":
						return res
					i += 1
					j += 1
					continue
				if part.prefix and not segment.startswith(part.prefix):
					return None
				if part.variable:
					value = segment[len(part.prefix) :] if part.prefix else segment
					if context is not None and part.variable in context:
						if context[part.variable] != value:
							return None
					else:
						res[part.variable] = value
			i += 1
			j += 1
		if j != len(parts):
			return None
		if i == len(scope):
			return res
		if i == len(scope) - 1:
			part = scope[i]
			if isinstance(part, ScopeMatch) and part.wildcard == "**":
				return res
		return None

	def matchScopes(
		self,
		scopes: list[Scope] | None,
		path: str,
		context: ScopeContext | dict[str, ConstraintArg] | None = None,
	) -> ScopeContext | None:
		"""Matches a list of `scopes` patterns against the provided `path` using optional `context`."""
		if scopes:
			for item in reversed(scopes):
				matched = self.matchScope(item, path, context)
				if matched is not None:
					return matched
		return None

	def expandValue(
		self, value: ConstraintArg, context: dict[str, ConstraintArg]
	) -> ConstraintArg:
		"""Recursively expands placeholder variables like `${var}` in `value` using `context`."""
		if isinstance(value, str):
			match = _CTX_RE.match(value)
			if not match:
				return value
			varname = match.group("varname")
			if varname not in context:
				raise ValueError(f"Unknown variable in context: {varname}")
			return context[varname]
		if isinstance(value, list):
			changed = False
			res = list(value)
			for i, item in enumerate(value):
				expanded = self.expandValue(cast(ConstraintArg, item), context)
				if expanded != item:
					res[i] = expanded
					changed = True
			return res if changed else value
		if isinstance(value, dict):
			changed = False
			res_dict: dict[str, ConstraintArg] = dict(value)
			for key, item in value.items():
				expanded = self.expandValue(cast(ConstraintArg, item), context)
				if expanded != item:
					res_dict[key] = expanded
					changed = True
			return cast(ConstraintArg, res_dict if changed else value)
		return value

	def matchConstraint(
		self, constraint: Constraint, context: dict[str, ConstraintArg]
	) -> bool | Awaitable[bool]:
		"""Evaluates a single `constraint` against the provided `context` using runtime predicates."""
		if constraint.op not in self.runtime:
			raise ValueError(
				f"Constraint predicate not defined in runtime: {constraint.op}"
			)
		predicate = self.runtime[constraint.op]
		args = [self.expandValue(arg, context) for arg in constraint.args]
		return predicate(*args)

	def matchConstraints(
		self,
		constraints: list[Constraint] | None,
		context: dict[str, ConstraintArg],
	) -> bool | Awaitable[bool]:
		"""Evaluates a list of `constraints` against the provided `context`."""
		if not constraints:
			return True
		promises: list[Awaitable[bool]] = []
		for item in constraints:
			result = self.matchConstraint(item, context)
			if isawaitable(result):
				promises.append(result)
			elif not result:
				return False
		if promises:

			async def awaited() -> bool:
				for promise in promises:
					if not await promise:
						return False
				return True

			return awaited()
		return True


def action(text: str) -> Action:
	"""Creates an Action representation from the given `text`."""
	return text


def scope(text: str) -> Scope:
	"""Parses a path pattern string `text` into a compiled Scope list of segments and matches."""
	res: Scope = []
	for chunk in text.split("/"):
		if not chunk:
			continue
		match = _SCOPE_RE.search(chunk)
		if match:
			res.append(
				ScopeMatch(
					prefix=match.group("prefix"),
					variable=match.group("variable"),
					wildcard=match.group("wildcard"),
				)
			)
		else:
			res.append(chunk)
	return res


def capability(
	subject: None | str | list[str] | Scope | list[Scope],
	actions: Action | list[Action],
	object: str | list[str] | Scope | list[Scope],
	*constraints: Constraint,
) -> Capability:
	"""Creates a Capability defined by `subject`, `actions`, `object`, and any additional `constraints`."""
	def asScopes(value: str | list[str] | Scope | list[Scope]) -> list[Scope]:
		if isinstance(value, str):
			return [scope(value)]
		if isinstance(value, list):
			if not value:
				return []
			first = value[0]
			if isinstance(first, str):
				return [scope(item) for item in cast(list[str], value)]
			return cast(list[Scope], value)
		return [value]

	return Capability(
		subject=asScopes(subject) if subject is not None else None,
		object=asScopes(object),
		actions=[action(item) for item in actions]
		if isinstance(actions, list)
		else [action(actions)],
		where=list(constraints) if constraints else None,
	)


def constraint(op: str, *args: ConstraintArg) -> Constraint:
	"""Creates a dynamic Constraint with operation name `op` and list of `args`."""
	return Constraint(op=op, args=list(args))


def can(*actions: Action) -> Callable[..., Capability | None]:
	"""Helper to create a capability factory function targeting specific `actions`."""
	def factory(*scopes: str) -> Capability | None:
		if not scopes:
			return None
		return capability(None, list(actions), [scope(item) for item in scopes])

	return factory


Operations: dict[str, Callable[..., Constraint]] = {}


class Where:
	"""Generates Constraint builders dynamically using attribute lookup."""

	def __getattr__(self, name: str) -> Callable[..., Constraint]:
		if name not in Operations:
			Operations[name] = lambda *args, _name=name: constraint(_name, *args)
		return Operations[name]


where = Where()


# EOF
