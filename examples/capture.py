from extra import Service, HTTPRequest, HTTPResponse, on, run


# To send:
# curl -X POST -H "Content-Type: application/json" -d '{"key1":"value1", "key2":"value2"}' http://localhost:8000/data
class CaptureService(Service):
	@on(GET_POST="/{path:any}")
	async def catchall(self, request: HTTPRequest, path: str) -> HTTPResponse:
		chunks: list[bytes] = []
		# Reading the response body in one shot
		# raw = await request.body.load()
		# Or incrementally
		async for chunk in request.read():
			if chunk is None:
				break
			else:
				chunks.append(chunk)
				pass
		body: bytes = b"".join(chunks)
		print("Headers:", request.headers)
		print("Body:", body)
		return request.returns(
			{
				"method": request.method,
				"path": request.path,
				"headers": request.headers,
				"body": body.decode("ascii"),
			}
		)


# NOTE: You can start this with `uvicorn helloworld:app`
# app = mount(CaptureService)

if __name__ == "__main__":
	run(CaptureService())

# EOF
