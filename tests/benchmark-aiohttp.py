from aiohttp import web
import os

PORT: int = int(os.getenv("HTTP_PORT", 8000))


async def hello(request):
    return web.Response(text="Hello, World!")


app = web.Application()
app.add_routes([web.get("/", hello)])
host = "0.0.0.0"
print(f"AIOHTTP server on {host}:{PORT}")
web.run_app(app, host=host, port=PORT)
# EOF
