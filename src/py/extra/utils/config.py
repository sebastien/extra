from os import getenv

PORT: int = int(getenv("PORT", 8000))
HOST: str = getenv("HOST", "0.0.0.0")

# EOF
