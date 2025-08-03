from extra import Service, HTTPRequest, HTTPResponse, on, run
from hashlib import sha256

# --
# # Complete read
#
# Loads arbitrary requests and outputs the read size. They both should be the
# the same.


def sha(data: bytes) -> str:
	return sha256(data).hexdigest()


class BodyLengthService(Service):
	@on(GET_POST="/{path:any}")
	async def read(self, request: HTTPRequest, path: str) -> HTTPResponse:
		body = await request.body.load()
		print(f"[extra]  Server received body: {sha(body)} {len(body)}")
		return request.respond(
			b"Read:%s %d" % (sha(body).encode(), len(body)), b"text/plain"
		)


if __name__ == "__main__":
	run(BodyLengthService())
# EOF
