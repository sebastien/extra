from extra.features.cors import ANY, allow, matches, origins, setCORSHeaders
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

strict = origins(host=["localhost", "minibench"], port=[None, 8000], scheme=["http"])
if "http://localhost" not in strict or "http://localhost:8000" not in strict:
	print("FAIL: origins aliases should generate concrete origin values")
	failed += 1

wild = origins(host=["localhost", "little.onl"], port=[ANY], subdomain=[None, ANY], scheme=["http", "https"])
if not matches("http://localhost:*", "http://localhost:9999"):
	print("FAIL: wildcard port pattern should match explicit ports")
	failed += 1
if not matches("https://*.little.onl:*", "https://development.little.onl:444"):
	print("FAIL: wildcard subdomain pattern should match nested hosts")
	failed += 1
if matches("https://*.little.onl:*", "https://little.onl:444"):
	print("FAIL: wildcard subdomain should not match the bare host")
	failed += 1

allowed = strict + wild
if allow("http://minibench:8000", allowed) != "http://minibench:8000":
	print("FAIL: allow should preserve a matching concrete origin")
	failed += 1
if allow("http://localhost:9000", strict) is not None:
	print("FAIL: strict origins should reject undeclared ports")
	failed += 1
if allow("https://app.little.onl:8443", allowed) != "https://app.little.onl:8443":
	print("FAIL: wildcard origin patterns should allow matching origins")
	failed += 1

if failed:
	print(f"FAIL {failed} tests failed")
	print("ERR")
else:
	print("OK! All tests passed")
	print("EOK")


# EOF
