import json
import sys
import tempfile
import types
from pathlib import Path

toon_mod = types.ModuleType("toon_format")


def decode(source: str):
	samples = {
		"name: Alice\nage: 30\n": {"name": "Alice", "age": 30},
		"items[2]: apple,banana\n": {"items": ["apple", "banana"]},
		"title: Extra\nvalue: 42\n": {"title": "Extra", "value": 42},
	}
	return samples[source]


toon_mod.decode = decode
sys.modules["toon_format"] = toon_mod

from extra.handler import AWSLambdaEvent
from extra.services.files import FileService


def makeRequest(path: str, method: str = "GET"):
	return AWSLambdaEvent.AsRequest(AWSLambdaEvent.Create(method, path))


failed = 0

with tempfile.TemporaryDirectory(prefix="extra-files-toon-") as tmp:
	root = Path(tmp)
	(root / "user.toon").write_text("name: Alice\nage: 30\n", encoding="utf8")
	(root / "bundle.toon.json").write_text("items[2]: apple,banana\n", encoding="utf8")
	(root / "fallback.toon").write_text("title: Extra\nvalue: 42\n", encoding="utf8")

	svc = FileService(root=root)

	res_toon = svc.read(makeRequest("/user.toon"), "user.toon")
	if res_toon.getHeader("Content-Type") != "application/json":
		print("FAIL: expected .toon to serve as application/json")
		failed += 1
	body_toon = (res_toon.body.payload if res_toon.body else b"").decode("utf8")
	if json.loads(body_toon) != {"name": "Alice", "age": 30}:
		print("FAIL: expected .toon payload to be decoded to JSON")
		failed += 1

	res_toon_json = svc.read(makeRequest("/bundle.toon.json"), "bundle.toon.json")
	if res_toon_json.getHeader("Content-Type") != "application/json":
		print("FAIL: expected .toon.json to serve as application/json")
		failed += 1
	body_toon_json = (res_toon_json.body.payload if res_toon_json.body else b"").decode(
		"utf8"
	)
	if json.loads(body_toon_json) != {"items": ["apple", "banana"]}:
		print("FAIL: expected .toon.json payload to be decoded to JSON")
		failed += 1

	res_fallback = svc.read(makeRequest("/fallback.json"), "fallback.json")
	if res_fallback.getHeader("Content-Type") != "application/json":
		print("FAIL: expected .json request to fall back to .toon and serve JSON")
		failed += 1
	body_fallback = (res_fallback.body.payload if res_fallback.body else b"").decode(
		"utf8"
	)
	if json.loads(body_fallback) != {"title": "Extra", "value": 42}:
		print("FAIL: expected .json fallback to decode the .toon source")
		failed += 1

	res_head = svc.head(makeRequest("/user.toon", method="HEAD"), "user.toon")
	if res_head.getHeader("Content-Type") != "application/json":
		print("FAIL: expected HEAD for .toon to preserve application/json")
		failed += 1
	if res_head.body is not None:
		print("FAIL: expected HEAD for .toon to have no body")
		failed += 1

	resolved, redirect = svc.resolvePath("fallback.json")
	if resolved != (root / "fallback.toon").resolve() or redirect is not None:
		print("FAIL: expected .json resolution to prefer a matching .toon file")
		failed += 1

if failed:
	print(f"FAIL {failed} tests failed")
	print("ERR")
else:
	print("OK! All tests passed")
	print("EOK")


# EOF
