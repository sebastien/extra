from aiohttp import web
from hashlib import sha256


def sha(data: bytes) -> str:
	return sha256(data).hexdigest()


async def handle(request):
	try:
		data = await request.read()
		print(f"[aiohttp] Server received body: {sha(data)} {len(data)}")
		return web.Response(text=f"Read:{sha(data)} {len(data)}")
	except Exception as e:
		return web.Response(text=f"Error:{str(e)}\n", status=500)


app = web.Application()
app.router.add_route("GET", "/{tail:.*}", handle)
app.router.add_route("POST", "/{tail:.*}", handle)

if __name__ == "__main__":
	web.run_app(app, host="0.0.0.0", port=8000)
# EOF
