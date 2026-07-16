from extra import Service, on, run


class API(Service):
	@on(GET="/")
	def hello(self, request):
		return request.respondText(b"Hello, World!")


if __name__ == "__main__":
	# Quiet logs for load tests (request logging + filled stderr pipes stall servers)
	run(API(), logRequests=False)

# EOF
