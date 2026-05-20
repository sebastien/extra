import tempfile
from pathlib import Path

from extra.handler import AWSLambdaEvent
from extra.services.files import FileService


def makeRequest(path: str):
	return AWSLambdaEvent.AsRequest(AWSLambdaEvent.Create("GET", path))


failed = 0

with tempfile.TemporaryDirectory(prefix="extra-files-ssi-") as tmp:
	root = Path(tmp)

	(root / "page.shtml").write_text("<h1>SHTML</h1>", encoding="utf8")
	(root / "view.shtm").write_text("<h1>SHTM</h1>", encoding="utf8")

	(root / "frag.html").write_text("<p>fragment</p>", encoding="utf8")
	(root / "nested").mkdir()
	(root / "nested" / "local.txt").write_text("<em>local</em>", encoding="utf8")
	(root / "nested" / "page.shtml").write_text(
		"A<!--#include file=\"local.txt\" -->B<!--#include virtual=\"/frag.html\" -->C",
		encoding="utf8",
	)

	(root / "unsafe.shtml").write_text(
		"X<!--#include virtual=\"/../etc/passwd\" -->Y", encoding="utf8"
	)

	(root / "loop.shtml").write_text(
		"L<!--#include file=\"loop.shtml\" -->R", encoding="utf8"
	)
	(root / "meta.txt").write_text("abcdef", encoding="utf8")
	(root / "vars.shtml").write_text(
		"""
		<!--#set var="NAME" value="Extra" -->
		X<!--#echo var="NAME" -->Y
		<!--#if expr="${NAME} = Extra" -->OK<!--#elif expr="${NAME} = Nope" -->BAD<!--#else -->BAD<!--#endif -->
		<!--#if expr="${NAME} =~ ^Ex" -->R1<!--#endif -->
		<!--#if expr="${NAME} !~ ^No" -->R2<!--#endif -->
		""",
		encoding="utf8",
	)
	(root / "cfg.shtml").write_text(
		"""
		<!--#config sizefmt="bytes" timefmt="%Y" -->
		SIZE:<!--#fsize file="meta.txt" -->
		YEAR:<!--#flastmod file="meta.txt" -->
		""",
		encoding="utf8",
	)
	(root / "env.shtml").write_text("<!--#printenv -->", encoding="utf8")
	(root / "exec.shtml").write_text(
		"A<!--#exec cmd=\"echo hi\" -->B", encoding="utf8"
	)

	(root / "blog").mkdir()
	(root / "blog" / "index.shtml").write_text("<h1>Blog</h1>", encoding="utf8")

	svc = FileService(root=root)

	resolved_shtml, _ = svc.resolvePath("page")
	if resolved_shtml != (root / "page.shtml").resolve():
		print("FAIL: expected extensionless path to resolve .shtml")
		failed += 1

	resolved_shtm, _ = svc.resolvePath("view")
	if resolved_shtm != (root / "view.shtm").resolve():
		print("FAIL: expected extensionless path to resolve .shtm")
		failed += 1

	resolved_index, redirect = svc.resolvePath("blog")
	if resolved_index != (root / "blog" / "index.shtml").resolve() or redirect != "/blog/index.shtml":
		print("FAIL: expected directory to resolve index.shtml with redirect")
		failed += 1

	res = svc.read(makeRequest("/nested/page.shtml"), "nested/page.shtml")
	body = res.body.payload.decode("utf8") if res.body else ""
	if "A<em>local</em>B<p>fragment</p>C" not in body:
		print("FAIL: expected SSI includes to be expanded")
		failed += 1

	res_unsafe = svc.read(makeRequest("/unsafe.shtml"), "unsafe.shtml")
	body_unsafe = res_unsafe.body.payload.decode("utf8") if res_unsafe.body else ""
	if "#include virtual=\"/../etc/passwd\"" not in body_unsafe:
		print("FAIL: expected unsafe include to be preserved")
		failed += 1

	res_loop = svc.read(makeRequest("/loop.shtml"), "loop.shtml")
	body_loop = res_loop.body.payload.decode("utf8") if res_loop.body else ""
	if "#include file=\"loop.shtml\"" not in body_loop:
		print("FAIL: expected cyclic include to be preserved")
		failed += 1

	res_vars = svc.read(makeRequest("/vars.shtml"), "vars.shtml")
	body_vars = res_vars.body.payload.decode("utf8") if res_vars.body else ""
	if "XExtraY" not in body_vars or "OK" not in body_vars or "R1" not in body_vars or "R2" not in body_vars:
		print("FAIL: expected SSI set/echo/if directives to work")
		failed += 1
	if "BAD" in body_vars:
		print("FAIL: expected SSI if/elif/else branch selection")
		failed += 1

	res_cfg = svc.read(makeRequest("/cfg.shtml"), "cfg.shtml")
	body_cfg = res_cfg.body.payload.decode("utf8") if res_cfg.body else ""
	if "SIZE:6" not in body_cfg:
		print("FAIL: expected SSI fsize with bytes format")
		failed += 1
	if "YEAR:" not in body_cfg or len(body_cfg.split("YEAR:", 1)[1].strip()) < 4:
		print("FAIL: expected SSI flastmod output")
		failed += 1

	res_env = svc.read(makeRequest("/env.shtml"), "env.shtml")
	body_env = res_env.body.payload.decode("utf8") if res_env.body else ""
	if "DOCUMENT_NAME=env.shtml" not in body_env:
		print("FAIL: expected SSI printenv to expose variables")
		failed += 1

	res_exec = svc.read(makeRequest("/exec.shtml"), "exec.shtml")
	body_exec = res_exec.body.payload.decode("utf8") if res_exec.body else ""
	if "#exec cmd=\"echo hi\"" not in body_exec:
		print("FAIL: expected SSI exec directive to stay unprocessed")
		failed += 1

if failed:
	print(f"FAIL {failed} tests failed")
	print("ERR")
else:
	print("OK! All tests passed")
	print("EOK")


# EOF
