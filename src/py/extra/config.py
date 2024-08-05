from os import getenv
from .utils.io import DEFAULT_ENCODING  # NOQA: F401

PORT: int = int(getenv("PORT", 8000))

# If we're starting  Extra in a development environment, we want it to be accessible from everywhere
HOST: str = getenv("HOST", "0.0.0.0")  # nosec: B104

LOG_REQUESTS: bool = getenv("EXTRA_LOG_REQUESTS", "1") == "1"

# EOF
