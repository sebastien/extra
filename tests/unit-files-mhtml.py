import tempfile
from pathlib import Path

from extra.handler import AWSLambdaEvent
from extra.services.files import FileService


def makeRequest(path: str):
	return AWSLambdaEvent.AsRequest(AWSLambdaEvent.Create("GET", path))


failed = 0

MHTML_SAMPLE = """From: <Saved by Blink>
MIME-Version: 1.0
Content-Type: multipart/related; type="text/html"; boundary="----X"

------X
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable
Content-Location: https://example.com/page

<!doctype html><html><head>
<link rel=3D"stylesheet" href=3D"https://example.com/assets/font-files/texta.css">
</head><body>
<img src=3D"https://example.com/assets/images/logo.png">
</body></html>
------X
Content-Type: text/css; charset=UTF-8
Content-Transfer-Encoding: quoted-printable
Content-Location: https://example.com/assets/font-files/texta.css

@font-face { src: url(https://example.com/assets/fonts/a.woff2); }
------X
Content-Type: font/woff2
Content-Transfer-Encoding: base64
Content-Location: https://example.com/assets/fonts/a.woff2

QUJD
------X
Content-Type: image/png
Content-Transfer-Encoding: base64
Content-Location: https://example.com/assets/images/logo.png

QUJD
------X--
"""

with tempfile.TemporaryDirectory(prefix="extra-files-mhtml-") as tmp:
	root = Path(tmp)
	(root / "page.mhtml").write_text(MHTML_SAMPLE, encoding="utf8")
	(root / "page.mht").write_text(MHTML_SAMPLE, encoding="utf8")
	(root / "page.html").write_text("<html><body>ok</body></html>", encoding="utf8")
	svc = FileService(root=root)

	res_mhtml = svc.read(makeRequest("/page.mhtml"), "page.mhtml")
	if res_mhtml.getHeader("Content-Type") != "text/html":
		print("FAIL: expected .mhtml to render as text/html by default")
		failed += 1
	body_mhtml = (res_mhtml.body.payload if res_mhtml.body else b"").decode(
		"utf8", errors="replace"
	)
	if "/page.mhtml/assets/font-files/texta.css" not in body_mhtml:
		print("FAIL: expected .mhtml stylesheet URL to be remapped")
		failed += 1
	if "/page.mhtml/assets/images/logo.png" not in body_mhtml:
		print("FAIL: expected .mhtml image URL to be remapped")
		failed += 1

	res_asset_css = svc.read(
		makeRequest("/page.mhtml/assets/font-files/texta.css"),
		"page.mhtml/assets/font-files/texta.css",
	)
	if res_asset_css.getHeader("Content-Type") != "text/css":
		print("FAIL: expected virtual css asset content-type text/css")
		failed += 1
	body_css = (res_asset_css.body.payload if res_asset_css.body else b"").decode(
		"utf8", errors="replace"
	)
	if "/page.mhtml/assets/fonts/a.woff2" not in body_css:
		print("FAIL: expected css embedded URL to be remapped")
		failed += 1

	res_asset_logo = svc.read(
		makeRequest("/page.mhtml/assets/images/logo.png"),
		"page.mhtml/assets/images/logo.png",
	)
	if res_asset_logo.getHeader("Content-Type") != "image/png":
		print("FAIL: expected virtual image asset content-type image/png")
		failed += 1
	if (res_asset_logo.body.payload if res_asset_logo.body else b"") != b"ABC":
		print("FAIL: expected virtual image asset bytes")
		failed += 1

	res_asset_missing = svc.read(
		makeRequest("/page.mhtml/assets/fonts/missing.woff2"),
		"page.mhtml/assets/fonts/missing.woff2",
	)
	if res_asset_missing.status not in (301, 302, 307, 308):
		print("FAIL: expected missing virtual asset to redirect to original site")
		failed += 1
	if (
		res_asset_missing.getHeader("Location")
		!= "https://example.com/assets/fonts/missing.woff2"
	):
		print("FAIL: expected missing virtual asset redirect Location")
		failed += 1

	raw_request = AWSLambdaEvent.AsRequest(
		{
			"httpMethod": "GET",
			"path": "/page.mhtml",
			"queryStringParameters": {"raw": ""},
			"headers": {},
		}
	)
	res_mhtml_raw = svc.read(raw_request, "page.mhtml")
	if res_mhtml_raw.getHeader("Content-Type") != "multipart/related":
		print("FAIL: expected .mhtml?raw to return multipart/related")
		failed += 1

	res_mht = svc.read(makeRequest("/page.mht"), "page.mht")
	if res_mht.getHeader("Content-Type") != "text/html":
		print("FAIL: expected .mht to render as text/html by default")
		failed += 1

	res_html = svc.read(makeRequest("/page.html"), "page.html")
	if res_html.getHeader("Content-Type") != "text/html":
		print("FAIL: expected html files to keep normal text/html")
		failed += 1

if failed:
	print(f"FAIL {failed} tests failed")
	print("ERR")
else:
	print("OK! All tests passed")
	print("EOK")


# EOF
