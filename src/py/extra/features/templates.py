"""A small, JSON-oriented template language.

Supported directives are ``${name}``, ``${resolve:name}``, ``${if:expr}``,
``${elif:expr}``, ``${else}``, ``${for:name}``, ``${with:name}``,
``${empty}``, ``${end}``, and ``${T:en="Text",fr="Texte"}``.
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Sequence


__version__ = "1.0.0"
DEFAULT_LOCALE = "en"
DEFAULT_ENCODING = "utf-8"
TRANSLATE_DEFAULT = "default"
TRANSLATE_STRICT = "strict"


class TemplateError(Exception):
	"""Base exception for template parsing and rendering failures."""


class TemplateSyntaxError(TemplateError):
	"""Raised when a template contains an invalid directive structure."""


class TemplateEvaluationError(TemplateError):
	"""Raised when strict rendering cannot resolve a value."""


def _json(value: Any, *_: Any) -> str:
	return json.dumps(value)


def _escape_html(value: Any, *_: Any) -> str:
	return html.escape(str(value))


FORMATTERS: dict[str, Callable[..., Any]] = {
	"json": _json,
	"escapeHTML": _escape_html,
	"repr": lambda value, *_: repr(value),
}


_DIRECTIVE = re.compile(r"\$\{([^{}]*)\}")
_EXPRESSION = re.compile(
	r"^\s*([A-Za-z_][A-Za-z0-9_.]*)(?:\s*(==|!=|>=|<=|>|<)\s*(.*?)\s*)?$"
)
_TRANSLATION = re.compile(
	r"\s*([A-Za-z][A-Za-z0-9_-]*)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^,]*))\s*(?:,|$)"
)


@dataclass(slots=True)
class _Text:
	value: str


@dataclass(slots=True)
class _Resolve:
	name: str
	formats: list[str]
	attributes: list[str]


@dataclass(slots=True)
class _If:
	branches: list[tuple[str | None, list[Any]]]


@dataclass(slots=True)
class _For:
	name: str
	limit: int | None
	body: list[Any]
	empty: list[Any]


@dataclass(slots=True)
class _With:
	name: str
	body: list[Any]


@dataclass(slots=True)
class _Translation:
	values: dict[str, str]


class Type:
	def __init__(self) -> None:
		self.attributes: list[str] | None = None

	def setAttributes(self, attributes: list[str] | None) -> None:
		self.attributes = attributes

	def export(self) -> str | dict[str, Any]:
		if self.attributes:
			return {"value": "Any", "attributes": self.attributes}
		return "Any"


class ListType:
	def __init__(self) -> None:
		self.content: MapType | None = None

	def defineSlot(self, slotName: str, slotType: Any = None) -> Any:
		if self.content is None:
			self.content = MapType()
		if not isinstance(self.content, MapType):
			raise TemplateError("Incompatible list slot type")
		return self.content.defineSlot(slotName, slotType)

	def export(self) -> list[Any]:
		return [self.content.export() if self.content else Type().export()]


class MapType:
	def __init__(self) -> None:
		self.content: dict[str, Any] = {}
		self.order: list[str] = []

	def defineSlot(self, slotName: str, slotValue: Any = None) -> Any:
		if not isinstance(slotName, str):
			raise TemplateError("Slot names must be strings")
		name, _, rest = slotName.partition(".")
		if slotValue is None:
			slotValue = Type()
		if not rest:
			if name not in self.order:
				self.order.append(name)
			self.content[name] = slotValue
			return slotValue
		child = self.content.get(name)
		if not isinstance(child, MapType):
			child = MapType()
			self.content[name] = child
			if name not in self.order:
				self.order.append(name)
		return child.defineSlot(rest, slotValue)

	def export(self) -> dict[str, Any]:
		return {
			"order": self.order,
			"values": {
				key: value if isinstance(value, str) else value.export()
				for key, value in self.content.items()
			},
		}


class Template:
	"""Parse and render a template against dictionary-like data."""

	FORMATTERS = FORMATTERS

	@classmethod
	def EnsureUnicode(cls, value: Any, encoding: str | None = None) -> str:
		if isinstance(value, str):
			return value
		if isinstance(value, bytes):
			return value.decode(encoding or DEFAULT_ENCODING)
		return str(value)

	@classmethod
	def IsString(cls, value: Any) -> bool:
		return isinstance(value, str)

	@classmethod
	def Decompose(cls, source: str | bytes | None) -> list[Any]:
		return cls(source).nodes

	def __init__(self, source: str | bytes | None = "") -> None:
		self.encoding = DEFAULT_ENCODING
		self.defaultLocale = DEFAULT_LOCALE
		self.translateMode = TRANSLATE_DEFAULT
		self.postProcessors: list[Callable[[str, Template], str]] = []
		self.source = self.EnsureUnicode(source or "")
		self.nodes = self._parse(self.source)
		self.code = self.nodes

	def setSource(self, source: str | bytes | None = "") -> None:
		self.source = self.EnsureUnicode(source or "")
		self.nodes = self._parse(self.source)
		self.code = self.nodes

	def addPostProcessor(self, processor: Callable[[str, Template], str] | None) -> Template:
		if processor:
			self.postProcessors.append(processor)
		return self

	@classmethod
	def _parse(cls, source: str) -> list[Any]:
		parts: list[Any] = []
		position = 0
		for match in _DIRECTIVE.finditer(source):
			if match.start() > position:
				parts.append(_Text(source[position : match.start()]))
			parts.append(match.group(1))
			position = match.end()
		if position < len(source):
			parts.append(_Text(source[position:]))
		return cls._parse_block(parts, 0)[0]

	@classmethod
	def _parse_block(
		cls, tokens: list[Any], index: int, stops: set[str] | None = None
	) -> tuple[list[Any], int, str | None]:
		result: list[Any] = []
		stops = stops or set()
		while index < len(tokens):
			token = tokens[index]
			index += 1
			if isinstance(token, _Text):
				result.append(token)
				continue
			name, _, argument = token.partition(":")
			name = name.strip()
			argument = argument.strip()
			if name in stops:
				return result, index - 1, name
			if name == "end":
				return result, index - 1, "end"
			if name in {"else", "elif", "empty"}:
				raise TemplateSyntaxError(f"Unexpected ${{{token}}}")
			if name in {"if"}:
				branches: list[tuple[str | None, list[Any]]] = []
				body, index, stop = cls._parse_block(tokens, index, {"elif", "else", "end"})
				branches.append((argument, body))
				while stop == "elif":
					condition = tokens[index]
					index += 1
					condition_name, _, condition_arg = condition.partition(":")
					if condition_name.strip() != "elif":
						raise TemplateSyntaxError("Invalid elif directive")
					body, index, stop = cls._parse_block(tokens, index, {"elif", "else", "end"})
					branches.append((condition_arg.strip(), body))
				if stop == "else":
					index += 1
					body, index, stop = cls._parse_block(tokens, index, {"end"})
					branches.append((None, body))
				if stop != "end":
					raise TemplateSyntaxError("Missing ${end} for ${if}")
				index += 1
				result.append(_If(branches))
				continue
			if name == "for":
				parts = argument.split("|", 1)
				loop_name = parts[0].strip()
				limit = int(parts[1]) if len(parts) == 2 and parts[1].strip() else None
				body, index, stop = cls._parse_block(tokens, index, {"empty", "end"})
				empty: list[Any] = []
				if stop == "empty":
					index += 1
					empty, index, stop = cls._parse_block(tokens, index, {"end"})
				if stop != "end":
					raise TemplateSyntaxError("Missing ${end} for ${for}")
				index += 1
				result.append(_For(loop_name, limit, body, empty))
				continue
			if name == "with":
				body, index, stop = cls._parse_block(tokens, index, {"end"})
				if stop != "end":
					raise TemplateSyntaxError("Missing ${end} for ${with}")
				index += 1
				result.append(_With(argument, body))
				continue
			if name == "T":
				result.append(_Translation(cls._parse_translation(argument)))
				continue
			result.append(cls._parse_resolve(token))
		return result, index, None

	@staticmethod
	def _parse_resolve(token: str) -> _Resolve:
		name, separator, formats_text = token.partition("|")
		if name.startswith("resolve:"):
			name = name[8:]
		attributes: list[str] = []
		if ":" in name:
			name, attributes_text = name.split(":", 1)
			attributes = [item.strip() for item in attributes_text.split(",") if item.strip()]
		formats = formats_text.split("+") if separator else []
		if not name or any(not item for item in formats):
			raise TemplateSyntaxError(f"Invalid variable directive: ${{{token}}}")
		return _Resolve(name, formats, attributes)

	@staticmethod
	def _parse_translation(argument: str) -> dict[str, str]:
		values: dict[str, str] = {}
		position = 0
		while position < len(argument):
			match = _TRANSLATION.match(argument, position)
			if not match:
				raise TemplateSyntaxError(f"Invalid translation: {argument}")
			values[match.group(1).lower()] = next(
				(value for value in match.groups()[1:] if value is not None), ""
			)
			position = match.end()
		return values

	def listVariables(self) -> list[str]:
		result: list[str] = []
		seen: set[str] = set()
		for node in self._walk(self.nodes):
			name: str | None = None
			if isinstance(node, _Resolve):
				name = node.name
			elif isinstance(node, (_For, _With)):
				name = node.name
			elif isinstance(node, _If):
				for expression, _ in node.branches:
					if expression:
						match = _EXPRESSION.match(expression)
						if match and match.group(1) not in seen:
							seen.add(match.group(1))
							result.append(match.group(1))
					name = None
			if name and name not in seen and name != "this":
				seen.add(name)
				result.append(name)
		return result

	@classmethod
	def _walk(cls, nodes: Iterable[Any]) -> Iterable[Any]:
		for node in nodes:
			yield node
			if isinstance(node, (_If, _For, _With)):
				branches = node.branches if isinstance(node, _If) else [(None, node.body)]
				for _, body in branches:
					yield from cls._walk(body)
				if isinstance(node, _For):
					yield from cls._walk(node.empty)

	def getInformation(self) -> MapType:
		result = MapType()
		for name in self.listVariables():
			result.defineSlot(name)
		return result

	@staticmethod
	def _resolve(name: str, scopes: Sequence[Any]) -> Any:
		parts = name.split(".")
		candidates = scopes if parts[0] != "this" else scopes[:1]
		for scope in candidates:
			value = scope
			try:
				for part in parts:
					if isinstance(value, Mapping):
						value = value.get(part)
					elif isinstance(value, (list, tuple)):
						value = value[int(part)]
					else:
						value = getattr(value, part, None)
					if value is None:
						break
				else:
					return value
			except (IndexError, KeyError, TypeError, ValueError):
				pass
		return None

	@classmethod
	def _literal(cls, value: str) -> Any:
		try:
			return json.loads(value)
		except json.JSONDecodeError:
			return value.strip("\"'")

	def _evaluate(self, expression: str, scopes: Sequence[Any]) -> bool:
		if expression.endswith("?") and not any(op in expression for op in ("==", "!=", ">=", "<=", ">", "<")):
			value = self._resolve(expression[:-1].strip(), scopes)
			return bool(value)
		match = _EXPRESSION.match(expression)
		if not match:
			raise TemplateSyntaxError(f"Invalid expression: {expression}")
		left = self._resolve(match.group(1), scopes)
		if not match.group(2):
			return bool(left)
		right = self._literal(match.group(3) or "")
		operator = match.group(2)
		try:
			comparisons: dict[str, bool] = {
				"==": left == right,
				"!=": left != right,
				">": left > right,
				"<": left < right,
				">=": left >= right,
				"<=": left <= right,
			}
			return comparisons[operator]
		except TypeError:
			return False

	def apply(
		self,
		context: Any,
		locale: str | None = None,
		strict: bool | None = None,
		formatters: Mapping[str, Callable[..., Any]] | None = None,
	) -> str:
		locale = locale or self.defaultLocale
		strict = bool(strict)
		active_formatters = formatters or self.FORMATTERS
		result = self._render(self.nodes, [context], locale, strict, active_formatters)
		for processor in self.postProcessors:
			result = processor(result, self)
		return result

	def _render(
		self,
		nodes: Iterable[Any],
		scopes: list[Any],
		locale: str,
		strict: bool,
		formatters: Mapping[str, Callable[..., Any]],
	) -> str:
		result: list[str] = []
		for node in nodes:
			if isinstance(node, _Text):
				result.append(node.value)
			elif isinstance(node, _Resolve):
				value = self._resolve(node.name, scopes)
				if value is None:
					if strict:
						raise TemplateEvaluationError(f"Missing variable {node.name}")
					result.append(f"[[ERROR: Missing variable {node.name}]]")
					continue
				if isinstance(value, Mapping) and locale in value:
					value = value[locale]
				for formatter_name in node.formats:
					formatter = formatters.get(formatter_name)
					if formatter is None:
						raise TemplateEvaluationError(f"Unknown formatter {formatter_name}")
					value = formatter(value, locale, node)
				result.append(self.EnsureUnicode(value, self.encoding))
			elif isinstance(node, _Translation):
				value = node.values.get(locale) or node.values.get(self.defaultLocale)
				if value is None:
					if strict or self.translateMode == TRANSLATE_STRICT:
						raise TemplateEvaluationError(f"Missing translation for locale {locale}")
					result.append(f"[[ERROR: Missing translation for locale {locale}]]")
				else:
					result.append(value)
			elif isinstance(node, _If):
				for expression, body in node.branches:
					if expression is None or self._evaluate(expression, scopes):
						result.append(self._render(body, scopes, locale, strict, formatters))
						break
			elif isinstance(node, _For):
				collection = self._resolve(node.name, scopes)
				values = list(collection.values()) if isinstance(collection, Mapping) else list(collection) if isinstance(collection, (list, tuple)) else []
				if not values:
					result.append(self._render(node.empty, scopes, locale, strict, formatters))
				else:
					for index, value in enumerate(values[: node.limit]):
						result.append(self._render(node.body, [{"this": value, "i": index}, *scopes], locale, strict, formatters))
			elif isinstance(node, _With):
				value = self._resolve(node.name, scopes)
				if value is not None:
					result.append(self._render(node.body, [value, *scopes], locale, strict, formatters))
		return "".join(result)


def run(args: list[str] | None = None) -> None:
	args = sys.argv[1:] if args is None else args
	for path in args:
		base, _ = path.rsplit(".", 1)
		data_path = base + ".json"
		if os.path.exists(data_path):
			with open(data_path, encoding=DEFAULT_ENCODING) as data_file:
				data = json.load(data_file)
		else:
			data = None
		with open(path, encoding=DEFAULT_ENCODING) as template_file:
			sys.stdout.write(Template(template_file.read()).apply(data))


# EOF
