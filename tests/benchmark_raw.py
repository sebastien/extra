# @desc Tests the absolute minimum baseline speed
# NOTE: You can start this with `uvicorn benchmark_raw:app`
async def app(scope, receive, send):
	assert scope["type"] == "http"
	await send(
		{
			"type": "http.response.start",
			"status": 200,
			"headers": [
				[b"content-type", b"text/plain"],
			],
		}
	)
	await send(
		{"type": "http.response.body", "body": b'{"Hello":"World"}', "more_body": False}
	)


# EOF
