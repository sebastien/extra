from extra.http.parser import HTTPParser

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
