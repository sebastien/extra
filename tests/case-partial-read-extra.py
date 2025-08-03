from extra import Service, HTTPRequest, HTTPResponse, on, run


class PartialService(Service):
	@on(GET_POST="/{path:any}")
	async def read(self, request: HTTPRequest, path: str) -> HTTPResponse:
		# chunk = await request.read(1024)
		chunk = await request.load()
		return request.respond(b"Read: %d" % (len(chunk)), b"text/plain")


if __name__ == "__main__":
	run(PartialService())

# EOF
