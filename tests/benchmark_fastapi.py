#!/usr/bin/env python
# NOTE: To run, `uvicorn benchmark_fastapi:app`
try:
    from fastapi import FastAPI
except ImportError:
    raise ImportError(
        "FastAPI not available, run: python -m pip install --user fastapi")

app = FastAPI()


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.get("/items/{item_id}")
def read_item(item_id: int, q: str = None):
    return {"item_id": item_id, "q": q}

# EOF
