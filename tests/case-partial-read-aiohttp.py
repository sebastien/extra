from aiohttp import web


async def handler(request):
	# Read the first 1024 bytes from the request body
	chunk = await request.content.read(1024)
	return web.Response(text=f"Read: {len(chunk)}")


app = web.Application()
app.router.add_post(r"/{path:.*}", handler)

web.run_app(app, port=8000)

# EOF
