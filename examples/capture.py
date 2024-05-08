from extra import Service, HTTPRequest, HTTPResponse, on, run


class CaptureService(Service):
    @on(GET_POST="/{path:any}")
    async def catchall(self, request: HTTPRequest, path: str) -> HTTPResponse:
        # while True:
        # 	chunk = await request.read()
        # 	if chunk is None:
        # 		break
        # 	else_
        # 		pass
        # Or
        # 1 - Puts the request on a spool
        # 2 - Post proceses the raw data
        await request.load()
        print("Headers:", request.headers)
        print("Body:", request.body.raw)
        return request.respond(b"OK", b"text/plain")


# NOTE: You can start this with `uvicorn helloworld:app`
# app = mount(CaptureService)

if __name__ == "__main__":
    run(CaptureService())

# EOF
