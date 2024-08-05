from .services.files import FileService
from .bridges.aio import run as aio_run

aio_run(FileService())
# EOF
