from extra import run
from extra.services.files import FileService


class FileServer(FileService): ...


app = run(FileServer())

# EOF
