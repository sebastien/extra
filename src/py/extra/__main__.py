from extra.bridge.aio import run, server
import importlib
module = importlib.import_module("helloworld")
# for i in range(100000):
#     for _ in module.app("GET", "hello/world"):
#         pass
s = server(module.HelloWorld())
run(s)
# EOF
