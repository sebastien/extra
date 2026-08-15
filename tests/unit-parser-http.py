from extra.http.parser import HTTPParser
from extra.http.model import HTTPRequest

# parser = HTTPParser()
# for atom in parser.feed(
#     b"GET /time/5 HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close"
# ):
#     print("ATOM A", atom)
# for atom in parser.feed(b"\r\n\r\n"):
#     print("ATOM B", atom)

parser = HTTPParser()
for i, chunk in enumerate(
	[
		b"GET /time/5 ",
		b"HTTP/1.1\r\nHost: ",
		b"127.0.0.1\r",
		b"\nConn",
		b"ection: close\r\n",
		b"\r",
		b"\n",
	]
):
	for atom in parser.feed(chunk):
		print(i, atom)


parser = HTTPParser(requestsOnly=True)
atoms = list(
	parser.feed(
		b"PROPFIND / HTTP/1.1\r\nContent-Length: 11\r\n\r\n<propfind/>"
		b"GET /next HTTP/1.1\r\n\r\n"
	)
)
requests = [atom for atom in atoms if isinstance(atom, HTTPRequest)]
assert len(requests) == 2
assert requests[0].method == "PROPFIND"
assert requests[0].body.raw == b"<propfind/>"
assert requests[1].path == "/next"

# EOF
