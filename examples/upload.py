from extra import Service, HTTPRequest, HTTPResponse, on, expose, serve
from pathlib import Path

__doc__ = """\
An example of a development web server where local filesystem assets are
served with a live transformation phase.

You can easily test it with something like:

```
curl   -F "userid=1"   -F "filecomment=This is an image file"   -F "image=@/home/$(USER)/Pictures/1.jpg"   localhost:8000/upload
```

"""


class UploadService(Service):
    @expose(GET=("/", "/index"), contentType="text/html")
    def index(self) -> bytes:
        return b"<form action=/upload method=POST><input type=file /><button type=submit>Upload</button></form>"

    @on(POST="/upload")
    async def upload(self, request: HTTPRequest) -> HTTPResponse:
        file = await request.file()
        path = Path("data")
        path.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            f.write(file.read())
        return request.redirect(b"/")


# NOTE: You can start this with `uvicorn upload:app`
app = serve(UploadService)
# EOF
