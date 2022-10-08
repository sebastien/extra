from setuptools import setup
from mypyc.build import mypycify

# NOTE: This is experimental
setup(
    name="extra",
    packages=[
        "extra",
        "extra.bridge",
        "extra.feature",
        "extra.protocol",
        "extra.util",
        "extra.services",
    ],
    ext_modules=mypycify(
        [
            "src/py/extra/bridge/awslambda.py",
            "src/py/extra/bridge/cli.py",
            "src/py/extra/bridge/python.py",
            "src/py/extra/bridge/aio.py",
            "src/py/extra/bridge/files.py",
            "src/py/extra/bridge/__init__.py",
            "src/py/extra/bridge/asgi.py",
            "src/py/extra/feature/cors.py",
            "src/py/extra/feature/channels.py",
            "src/py/extra/protocol/__init__.py",
            "src/py/extra/protocol/http.py",
            "src/py/extra/util/__init__.py",
            "src/py/extra/util/files.py",
            "src/py/extra/services/__init__.py",
            "src/py/extra/services/files.py",
            "src/py/extra/__init__.py",
            "src/py/extra/routing.py",
            "src/py/extra/decorators.py",
            "src/py/extra/logging.py",
            "src/py/extra/model.py",
        ]
    ),
)
