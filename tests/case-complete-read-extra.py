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
        chunk = await request.load() or b""
        print(f"[extra] Server received body: {sha(chunk)} {len(chunk)}")
        return request.respond(
            b"Read:%s %d" % (sha(chunk).encode(), len(chunk)), b"text/plain"
        )


if __name__ == "__main__":
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else "extra"
    if mode == "client":
        import random
        import urllib.request

        random.seed(512)

        for base in (100, 1_000, 10_000, 100_000, 1_000_000, 10_000_000):
            body = b"-".join(b"%d" % (_) for _ in range(base + random.randint(0, base)))
            print("--")
            sent = f"{sha(body)} {len(body)}"
            print(f"[client] Sending: {sent}")
            req = urllib.request.Request("http://localhost:8000/upload", data=body)
            with urllib.request.urlopen(req) as response:
                response_data = response.read().split(b":")[-1].decode("ascii")
                print("[client] Received", response_data)
                print("OK" if response_data == sent else "FAIL")
    elif mode == "aiohttp":
        from aiohttp import web

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
        web.run_app(app, host="0.0.0.0", port=8000)

    else:
        print("Serving")
        run(BodyLengthService())
# EOF
