from extra.http.model import HTTPProcessingStatus, HTTPRequest
from extra.http.parser import HTTPParser


failed = 0

# POST without Content-Length followed by pipelined GET in same frame.
parser = HTTPParser()
payload = (
	b"POST /a HTTP/1.1\r\n"
	b"Host: localhost\r\n"
	b"\r\n"
	b"GET /b HTTP/1.1\r\n"
	b"Host: localhost\r\n"
	b"\r\n"
)
requests = [atom for atom in parser.feed(payload) if isinstance(atom, HTTPRequest)]
paths = [_.path for _ in requests]
if paths != ["/a", "/b"]:
	print(f"FAIL: unexpected parsed request paths: {paths}")
	failed += 1

# Unsupported transfer encoding should be reported as bad format.
parser = HTTPParser()
chunked_payload = (
	b"POST /chunked HTTP/1.1\r\n"
	b"Host: localhost\r\n"
	b"Transfer-Encoding: chunked\r\n"
	b"\r\n"
	b"0\r\n\r\n"
)
atoms = list(parser.feed(chunked_payload))
if HTTPProcessingStatus.BadFormat not in atoms:
	print("FAIL: expected BadFormat for unsupported Transfer-Encoding")
	failed += 1

if failed:
	print(f"FAIL {failed} tests failed")
	print("ERR")
else:
	print("OK! All tests passed")
	print("EOK")


# EOF
