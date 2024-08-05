#!/usr/bin/env python
# NOTE: To run, `uvicorn benchmark-fastapi:app`
try:
    from fastapi import FastAPI
    from fastapi.responses import PlainTextResponse
except ImportError:
    raise ImportError(
        "FastAPI not available, run: python -m pip install --user fastapi"
    )

app = FastAPI()


@app.get("/", response_class=PlainTextResponse)
def read_root():
    return "Hello, World!"


# EOF
