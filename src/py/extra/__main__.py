from .server import run
from .services.files import FileService
from .utils.logging import info

info("Starting Extra in standalone local file server")
run(FileService())
# EOF
