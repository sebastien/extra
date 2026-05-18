import re
from datetime import datetime, timezone
from pathlib import Path

RE_DIRECTIVE = re.compile(r"<!--\s*#(.*?)\s*-->", re.DOTALL)
RE_ATTR = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s]+)")
RE_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
RE_DOCTYPE = re.compile(r"<!DOCTYPE\b[^>]*>\s*", re.IGNORECASE)


def _strip(value: str) -> str:
	if len(value) >= 2 and (
		(value[0] == '"' and value[-1] == '"') or (value[0] == "'" and value[-1] == "'")
	):
		return value[1:-1]
	return value


def _interpolate(value: str, variables: dict[str, str]) -> str:
	def repl(match: re.Match[str]) -> str:
		return variables.get(match.group(1), "")

	return RE_VAR.sub(repl, value)


def _parseDirective(content: str) -> tuple[str, dict[str, str]] | None:
	parts = content.strip().split(None, 1)
	if not parts:
		return None
	name = parts[0].lower()
	attributes: dict[str, str] = {}
	if len(parts) > 1:
		for key, value in RE_ATTR.findall(parts[1]):
			attributes[key.lower()] = _strip(value)
	return name, attributes


def _stripDoctype(source: str) -> str:
	return RE_DOCTYPE.sub("", source)


def _resolveTarget(kind: str, target: str, root: Path, current: Path) -> Path | None:
	if kind == "file":
		candidate = (current.parent / target).resolve(strict=False)
	elif kind == "virtual":
		# Apache-style "virtual" is URL-rooted when absolute (/...).
		# For compatibility, a relative virtual target is resolved from
		# the current document directory.
		candidate = (
			(root / target.lstrip("/")).resolve(strict=False)
			if target.startswith("/")
			else (current.parent / target).resolve(strict=False)
		)
	else:
		return None
	if not candidate.is_relative_to(root):
		return None
	return candidate


def _formatSize(path: Path, sizefmt: str) -> str:
	size = path.stat().st_size
	if sizefmt == "bytes":
		return str(size)
	if size < 1024:
		return f"{size}B"
	if size < 1024 * 1024:
		return f"{(size / 1024):.1f}K"
	return f"{(size / (1024 * 1024)):.1f}M"


def _formatTime(path: Path, timefmt: str) -> str:
	dt = datetime.fromtimestamp(path.stat().st_mtime)
	try:
		return dt.strftime(timefmt)
	except ValueError:
		return dt.ctime()


def _tokenize(expr: str) -> list[str]:
	tokens: list[str] = []
	i = 0
	n = len(expr)
	while i < n:
		c = expr[i]
		if c.isspace():
			i += 1
		elif i + 1 < n and expr[i : i + 2] in ("&&", "||", "!=", "=~", "!~"):
			tokens.append(expr[i : i + 2])
			i += 2
		elif c in "()=!":
			tokens.append(c)
			i += 1
		elif c in ('"', "'"):
			q = c
			j = i + 1
			while j < n and expr[j] != q:
				j += 1
			tokens.append(expr[i : j + 1])
			i = j + 1
		else:
			j = i
			while j < n and not expr[j].isspace() and expr[j] not in "()":
				if j + 1 < n and expr[j : j + 2] in ("&&", "||", "!=", "=~", "!~"):
					break
				j += 1
			tokens.append(expr[i:j])
			i = j
	return tokens


class _ExprParser:
	def __init__(self, tokens: list[str], variables: dict[str, str]):
		self.tokens = tokens
		self.variables = variables
		self.i = 0

	def _peek(self) -> str | None:
		return self.tokens[self.i] if self.i < len(self.tokens) else None

	def _eat(self, token: str) -> bool:
		if self._peek() == token:
			self.i += 1
			return True
		return False

	def _value(self) -> str:
		tok = self._peek()
		if tok is None:
			return ""
		self.i += 1
		if tok.startswith("${") and tok.endswith("}"):
			return self.variables.get(tok[2:-1], "")
		if (tok.startswith('"') and tok.endswith('"')) or (
			tok.startswith("'") and tok.endswith("'")
		):
			return tok[1:-1]
		return self.variables.get(tok, tok)

	def _factor(self) -> bool:
		if self._eat("!"):
			return not self._factor()
		if self._eat("("):
			res = self._expr()
			self._eat(")")
			return res
		left = self._value()
		op = self._peek()
		if op in ("=", "!=", "=~", "!~"):
			self.i += 1
			right = self._value()
			if op == "=":
				return left == right
			if op == "!=":
				return left != right
			try:
				matched = re.search(right, left) is not None
			except re.error:
				matched = False
			return matched if op == "=~" else not matched
		return bool(left)

	def _and(self) -> bool:
		res = self._factor()
		while self._eat("&&"):
			res = res and self._factor()
		return res

	def _expr(self) -> bool:
		res = self._and()
		while self._eat("||"):
			res = res or self._and()
		return res

	def parse(self) -> bool:
		return self._expr()


def _evalExpr(expr: str, variables: dict[str, str]) -> bool:
	tokens = _tokenize(_interpolate(expr, variables))
	if not tokens:
		return False
	return _ExprParser(tokens, variables).parse()


def processSSI(
	source: str,
	*,
	root: Path,
	current: Path,
	stripIncludedDoctype: bool = True,
	maxDepth: int = 16,
	seen: set[Path] | None = None,
	variables: dict[str, str] | None = None,
	config: dict[str, str] | None = None,
) -> str:
	"""Expands SSI directives in HTML-like content."""
	if maxDepth < 0:
		return source

	base_root = root.resolve()
	visited = set(seen or ())
	visited.add(current.resolve(strict=False))
	cfg = dict(config or {})
	if "timefmt" not in cfg:
		cfg["timefmt"] = "%c"
	if "sizefmt" not in cfg:
		cfg["sizefmt"] = "abbrev"
	if "errmsg" not in cfg:
		cfg["errmsg"] = "[an error occurred while processing this directive]"

	now_local = datetime.now()
	now_gmt = datetime.now(timezone.utc)
	stat = current.stat() if current.exists() else None
	vars_map: dict[str, str] = {
		"DOCUMENT_NAME": current.name,
		"DOCUMENT_URI": "/" + current.relative_to(base_root).as_posix()
		if current.is_relative_to(base_root)
		else current.as_posix(),
		"DATE_LOCAL": now_local.strftime(cfg["timefmt"]),
		"DATE_GMT": now_gmt.strftime(cfg["timefmt"]),
		"LAST_MODIFIED": (
			datetime.fromtimestamp(stat.st_mtime).strftime(cfg["timefmt"])
			if stat
			else ""
		),
	}
	if variables:
		vars_map.update(variables)

	out: list[str] = []
	stack: list[dict[str, bool]] = []

	def isActive() -> bool:
		return all(frame["active"] for frame in stack)

	def parseAndRun(raw_directive: str) -> str:
		parsed = _parseDirective(raw_directive)
		if not parsed:
			return f"<!--#{raw_directive}-->"
		name, attrs = parsed

		if name == "exec":
			return f"<!--#{raw_directive}-->"

		if name == "config":
			for k in ("timefmt", "sizefmt", "errmsg"):
				if k in attrs:
					cfg[k] = _interpolate(attrs[k], vars_map)
			return ""

		if name == "set":
			var = attrs.get("var")
			value = attrs.get("value", "")
			if not var:
				return cfg["errmsg"]
			vars_map[var] = _interpolate(value, vars_map)
			return ""

		if name == "echo":
			var = attrs.get("var")
			if not var:
				return cfg["errmsg"]
			return vars_map.get(var, "")

		if name == "printenv":
			return "\n".join(f"{k}={v}" for k, v in sorted(vars_map.items()))

		if name in ("fsize", "flastmod"):
			kind = (
				"file" if "file" in attrs else "virtual" if "virtual" in attrs else None
			)
			if not kind:
				return cfg["errmsg"]
			target = _interpolate(attrs[kind], vars_map)
			resolved = _resolveTarget(kind, target, base_root, current)
			if not resolved or not resolved.exists() or not resolved.is_file():
				return cfg["errmsg"]
			return (
				_formatSize(resolved, cfg["sizefmt"])
				if name == "fsize"
				else _formatTime(resolved, cfg["timefmt"])
			)

		if name == "include":
			kind = (
				"file" if "file" in attrs else "virtual" if "virtual" in attrs else None
			)
			if not kind:
				return f"<!--#{raw_directive}-->"
			target = _interpolate(attrs[kind], vars_map)
			resolved = _resolveTarget(kind, target, base_root, current)
			if (
				not resolved
				or resolved in visited
				or not resolved.exists()
				or not resolved.is_file()
			):
				return f"<!--#{raw_directive}-->"
			try:
				included = resolved.read_text(encoding="utf8")
			except (UnicodeDecodeError, OSError):
				return f"<!--#{raw_directive}-->"
			if stripIncludedDoctype:
				included = _stripDoctype(included)
			return processSSI(
				included,
				root=base_root,
				current=resolved,
				stripIncludedDoctype=stripIncludedDoctype,
				maxDepth=maxDepth - 1,
				seen=visited | {resolved},
				variables=vars_map,
				config=cfg,
			)

		return f"<!--#{raw_directive}-->"

	offset = 0
	for match in RE_DIRECTIVE.finditer(source):
		start, end = match.span()
		if isActive():
			out.append(source[offset:start])
		raw_directive = match.group(1)
		parsed = _parseDirective(raw_directive)
		name = parsed[0] if parsed else None
		attrs = parsed[1] if parsed else {}

		if name == "if":
			parent_active = isActive()
			expr = attrs.get("expr", "")
			result = _evalExpr(expr, vars_map) if parent_active else False
			stack.append(
				{
					"parent": parent_active,
					"active": result,
					"satisfied": result,
					"else": False,
				}
			)
		elif name == "elif":
			if stack:
				frame = stack[-1]
				if frame["else"]:
					frame["active"] = False
				elif not frame["parent"]:
					frame["active"] = False
				elif frame["satisfied"]:
					frame["active"] = False
				else:
					expr = attrs.get("expr", "")
					result = _evalExpr(expr, vars_map)
					frame["active"] = result
					frame["satisfied"] = result
		elif name == "else":
			if stack:
				frame = stack[-1]
				frame["active"] = frame["parent"] and (not frame["satisfied"])
				frame["satisfied"] = True
				frame["else"] = True
		elif name == "endif":
			if stack:
				stack.pop()
		elif isActive():
			out.append(parseAndRun(raw_directive))
		offset = end

	if isActive():
		out.append(source[offset:])

	return "".join(out)


# EOF
