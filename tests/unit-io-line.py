from extra.utils.io import LineParser

parser = LineParser()


lines: list[bytes] = []
j: int = 0
for i, chunk in enumerate(
	[b"GET /time/5 HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close", b"\r\n\r", b"\n"]
):
	read: int = 0
	# We do this to prevent recursion
	offset: int = 0
	while j < 20:
		line, read = parser.feed(chunk, offset)
		if line is not None:
			lines.append(line)
		else:
			break
		offset += read
		j += 1

assert len(lines) == 4
for i, c in enumerate(
	b"GET /time/5 HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n".split(
		b"\r\n"
	)[:-1]
):
	assert bytes(lines[i]) == c

# EOF
