from extra.features.templates import (
	Template,
	TemplateEvaluationError,
	TemplateSyntaxError,
)


assert Template("Hello ${name}").apply({"name": "world"}) == "Hello world"
assert Template("${resolve:user.name}").apply({"user": {"name": "Ada"}}) == "Ada"
assert Template("${value|json}").apply({"value": {"ok": True}}) == '{"ok": true}'
assert (
	Template("${if:value>2}large${elif:value==2}two${else}small${end}").apply(
		{"value": 2}
	)
	== "two"
)
assert Template("${if:no}${if:yes}bad${else}bad${end}${else}ok${end}").apply(
	{"no": False, "yes": True}
) == "ok"
assert Template("${for:items}${i}:${this.name};${end}").apply(
	{"items": [{"name": "a"}, {"name": "b"}]}
) == "0:a;1:b;"
assert Template("${for:items}${this}${empty}empty${end}").apply(
	{"items": {"first": "A", "second": "B"}}
) == "AB"
assert Template("${for:items}${this}${empty}empty${end}").apply({"items": []}) == "empty"
assert Template("${with:user}${name}${end}").apply({"user": {"name": "Grace"}}) == "Grace"
assert Template("${T:en=Hello,fr=Bonjour}").apply({}, locale="fr") == "Bonjour"
assert Template("${if:value==null}yes${else}no${end}").apply(
	{"value": None}
) == "yes"

try:
	Template("${missing}").apply({}, strict=True)
	raise AssertionError("strict rendering should reject missing variables")
except TemplateEvaluationError:
	pass

try:
	Template("${if:value}missing")
	raise AssertionError("unclosed blocks should be rejected")
except TemplateSyntaxError:
	pass

for invalid in ("${for:items|nope}${end}", "${if:yes}${elif}"):
	try:
		Template(invalid)
		raise AssertionError("invalid template should be rejected")
	except TemplateSyntaxError:
		pass

context = {"items": [{"name": "a"}]}
Template("${for:items}${this.name}${end}").apply(context)
assert context == {"items": [{"name": "a"}]}

print("template feature tests passed")

# EOF
