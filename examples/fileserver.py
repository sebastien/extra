from extra import Service, Request, Response, on, run
from extra.services.files import FileService


class FileServer(FileService): ...


app = run(FilerSever)

# EOF
