from extra import Service, HTTPRequest, HTTPResponse, on, serve


class CaptureService(Service):

    @on(GET_POST="/upload")
    async def catchall(self, request: HTTPRequest) -> HTTPResponse:
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
        # The raw bytes
        request.body.raw
        # The value
        print(request.body.value)
        return request.respond(b"OK", b"text/plain")


# NOTE: You can start this with `uvicorn helloworld:app`
app = serve(CaptureService)
# EOF
