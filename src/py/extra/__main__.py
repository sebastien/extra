import importlib
module = importlib.import_module("helloworld")
for i in range(100000):
	for _  in module.app("GET", "hello/world"):
		pass
# EOF
