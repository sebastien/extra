from extra.features.cors import setCORSHeaders
from extra.http.model import HTTPResponse


failed = 0

res_any = setCORSHeaders(HTTPResponse.Create(), allowAll=True)
if res_any.getHeader("Access-Control-Allow-Origin") != "*":
	print("FAIL: wildcard CORS origin missing")
	failed += 1
if res_any.getHeader("Access-Control-Allow-Credentials") != "false":
	print("FAIL: wildcard CORS should not allow credentials")
	failed += 1

res_origin = setCORSHeaders(
	HTTPResponse.Create(),
	origin="https://example.com",
	allowAll=False,
)
if res_origin.getHeader("Access-Control-Allow-Origin") != "https://example.com":
	print("FAIL: explicit CORS origin not preserved")
	failed += 1
if res_origin.getHeader("Access-Control-Allow-Credentials") != "true":
	print("FAIL: explicit CORS origin should allow credentials")
	failed += 1
if res_origin.getHeader("Vary") != "Origin":
	print("FAIL: missing Vary: Origin header")
	failed += 1

if failed:
	print(f"FAIL {failed} tests failed")
	print("ERR")
else:
	print("OK! All tests passed")
	print("EOK")


# EOF
