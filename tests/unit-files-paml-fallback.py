import tempfile
from pathlib import Path

from extra.handler import AWSLambdaEvent
from extra.services import files as files_mod
from extra.services.files import FileService


def makeRequest(path: str):
	return AWSLambdaEvent.AsRequest(AWSLambdaEvent.Create("GET", path))


failed = 0

with tempfile.TemporaryDirectory(prefix="extra-files-paml-") as tmp:
	root = Path(tmp)

	(root / "page.paml").write_text("<p:Hello, Paml!", encoding="utf8")

	svc = FileService(root=root)
	resolved, redirect = svc.resolvePath("page.html")

	if files_mod._paml_engine is not None:
		if resolved != (root / "page.paml").resolve() or redirect is not None:
			print("FAIL: expected .html to resolve to .paml when Paml is enabled")
			failed += 1

		res = svc.read(makeRequest("/page.html"), "page.html")
		if res.getHeader("Content-Type") != "text/html":
			print("FAIL: expected .html->.paml fallback to render as text/html")
			failed += 1
		body = res.body.payload.decode("utf8") if res.body else ""
		if "Hello, Paml!" not in body:
			print("FAIL: expected .paml content to be rendered for .html request")
			failed += 1
	else:
		if resolved is not None:
			print("FAIL: expected .html to stay unresolved when Paml is disabled")
			failed += 1

		res = svc.read(makeRequest("/page.html"), "page.html")
		if res.status != 403:
			print(
				"FAIL: expected .html request to stay unauthorized when Paml is disabled"
			)
			failed += 1

if failed:
	print(f"FAIL {failed} tests failed")
	print("ERR")
else:
	print("OK! All tests passed")
	print("EOK")


# EOF
