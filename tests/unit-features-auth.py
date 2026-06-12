from extra.features.auth import bearerTokenAuth
from extra.features.capabilities import can, CapabilityMatcher, capability, constraint, scope, where
from extra.features.jwt import key, parse, sign
from extra.features.tokens import decode, encode, token
from extra.http.model import HTTPHeaders, HTTPRequest


failed = 0

matcher = CapabilityMatcher({"MatchesScope": lambda pattern, value: value.startswith(pattern)})
cap = capability(
	"/user/{user}",
	["Read"],
	"/files/{user}",
	where.MatchesScope("/files", "${object}"),
)
matched = matcher.match("/user/alice", "Read", "/files/alice", cap)
if matched is not True:
	print("FAIL: capability matcher should allow matching subject/object")
	failed += 1

if matcher.match("/user/alice", "Read", "/files/alice/private", cap) is not False:
	print("FAIL: capability matcher should reject trailing object segments")
	failed += 1

if matcher.match("/user/alice/private", "Read", "/files/alice", cap) is not False:
	print("FAIL: capability matcher should reject trailing subject segments")
	failed += 1

wild = CapabilityMatcher()
if wild.matchScope(scope("/files/*"), "/files/alice/private") is not None:
	print("FAIL: single wildcard should match exactly one segment")
	failed += 1
if wild.matchScope(scope("/files/**"), "/files/alice/private") is None:
	print("FAIL: double wildcard should match remaining segments")
	failed += 1

cap_any_subject = can("Read")("/public/{name}")
if cap_any_subject is None:
	print("FAIL: can() should create a capability")
	failed += 1
elif matcher.match("/user/anyone", "Read", "/public/alice", cap_any_subject) is not True:
	print("FAIL: subjectless capability should match any subject")
	failed += 1

tok = token(scope("/user/alice"), [cap], [])
encoded = encode(tok)
decoded = decode(encoded)
if encode(decoded) != encoded:
	print("FAIL: token codec should round-trip encoded tokens")
	failed += 1

cap_with_args = capability(
	None,
	["Read"],
	"/data/{id}",
	constraint("Matches", "a,b:c|d", {"v": [1, "2"]}, [True, None, 3.5]),
)
tok_with_args = token(scope("/user/alice"), [cap_with_args], [])
roundtrip = decode(encode(tok_with_args))
if roundtrip.capabilities[0].where is None or roundtrip.capabilities[0].where[0].args != cap_with_args.where[0].args:
	print("FAIL: token codec should preserve structured constraint args")
	failed += 1

secret = key()
signed = sign(tok, secret)
parsed = parse(signed, secret)
if parsed is None or encode(parsed) != encoded:
	print("FAIL: jwt sign/parse should preserve token payload")
	failed += 1

auth = bearerTokenAuth(secret)
request = HTTPRequest(
	method="GET",
	path="/secure",
	query=None,
	headers=HTTPHeaders({"Authorization": f"Bearer {signed}"}),
	body=None,
)
resolved = auth.resolve(request)
if resolved is None or encode(resolved) != encoded:
	print("FAIL: bearer token auth should resolve Authorization header")
	failed += 1

bad_request = HTTPRequest(
	method="GET",
	path="/secure",
	query=None,
	headers=HTTPHeaders({"Authorization": "Bearer invalid.token.value"}),
	body=None,
)
if auth.resolve(bad_request) is not None:
	print("FAIL: bearer token auth should reject invalid tokens")
	failed += 1

if failed:
	print(f"FAIL {failed} tests failed")
	print("ERR")
else:
	print("OK! All tests passed")
	print("EOK")


# EOF
