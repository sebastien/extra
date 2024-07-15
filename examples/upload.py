from extra import Service, HTTPRequest, HTTPResponse, on, expose, run
from pathlib import Path

__doc__ = """\
An example of a development web server where local filesystem assets are
served with a live transformation phase.

You can easily test it with something like:

```
curl 'https://cataas.com/cat/calico' > calico.jpg
curl   -F "userid=1" -F "filecomment=This is an image file" -F "image=@calico.jpg" http://localhost:8000/upload
```

"""


class UploadService(Service):

    @expose(GET=("/", "/index"), contentType="text/html", raw=True)
    def index(self) -> str:
        return "<form action=/upload method=POST><input type=file /><button type=submit>Upload</button></form>"

    @on(POST="/upload")
    async def upload(self, request: HTTPRequest) -> HTTPResponse:
        body = request.body
        data = await body.load()
        # print("file:", file)
        # path = Path("data")
        # path.mkdir(parents=True, exist_ok=True)
        # with path.open("wb") as f:
        #     f.write(file.read())
        return request.returns({"loaded": len(data)})


if __name__ == "__main__":

    run(UploadService())
# EOF
