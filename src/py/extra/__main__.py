from .server import run
from .services.files import FileService
from .utils.logging import info
from . import config  # NOQA: F401

info("Starting Extra in standalone local file server")
run(FileService())
# EOF
