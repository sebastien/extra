import asyncio
from dataclasses import replace as dataclassReplace
from xml.etree import ElementTree as ET

from extra.features.webdav import (
	MemoryWebDAVBackend,
	WebDAVService,
)
from extra.handler import AWSLambdaEvent
from extra.http.model import HTTPBodyBlob


def request(
	method: str, path: str, headers: dict[str, str] | None = None, body: str = ""
):
	return AWSLambdaEvent.AsRequest(AWSLambdaEvent.Create(method, path, headers, body))


backend = MemoryWebDAVBackend(
	{"/docs/hello world.txt": "hello", "/private/secret.txt": "secret"},
	collections=["/empty"],
)
service = WebDAVService(backend, canRead=lambda request, path, resource: path != "/private")


class AsyncChunks:
	def __init__(self, payload: bytes):
		self.payload = payload

	def __aiter__(self):
		return self

	async def __anext__(self):
		if self.payload:
			chunk, self.payload = self.payload[:2], self.payload[2:]
			return chunk
		raise StopAsyncIteration


class StreamingBackend(MemoryWebDAVBackend):
	async def open(self, path, start=None, end=None):
		return AsyncChunks(await super().open(path, start, end))


streaming = WebDAVService(StreamingBackend({"/stream.txt": "stream"}))
streamed = asyncio.run(streaming.read(request("GET", "/stream.txt"), "stream.txt"))


async def loadStream():
	chunks = []
	async for chunk in streamed.body.stream:
		if isinstance(chunk, bytes):
			chunks.append(chunk)
	return b"".join(chunks)


assert asyncio.run(loadStream()) == b"stream"


class HeadBackend(MemoryWebDAVBackend):
	opened = False

	async def open(self, path, start=None, end=None):
		self.opened = True
		return await super().open(path, start, end)


headBackend = HeadBackend({"/head.txt": "head"})
headService = WebDAVService(headBackend)
asyncio.run(headService.read(request("HEAD", "/head.txt"), "head.txt"))
assert not headBackend.opened

options = service.options(request("OPTIONS", "/"))
assert options.status == 200
assert options.getHeader("DAV") == "1"
assert options.getHeader("Allow") == "OPTIONS, GET, HEAD, PROPFIND"

noSlashOptions = service.options(request("OPTIONS", "/dav"))
assert noSlashOptions.status == 200

get = asyncio.run(service.read(request("GET", "/docs/hello%20world.txt"), "docs/hello%20world.txt"))
assert get.status == 200
assert isinstance(get.body, HTTPBodyBlob)
assert get.body.raw == b"hello"
assert get.getHeader("ETag")

ranged = asyncio.run(
	service.read(request("GET", "/docs/hello%20world.txt", {"Range": "bytes=1-3"}), "docs/hello%20world.txt")
)
assert ranged.status == 206
assert ranged.getHeader("Content-Range") == "bytes 1-3/5"
assert isinstance(ranged.body, HTTPBodyBlob)
assert ranged.body.raw == b"ell"

head = asyncio.run(service.read(request("HEAD", "/docs/hello%20world.txt"), "docs/hello%20world.txt"))
assert head.status == 200
assert head.body is None
assert head.getHeader("Content-Length") == "5"

body = '<?xml version="1.0"?><D:propfind xmlns:D="DAV:"><D:prop><D:displayname/><D:getetag/><D:unknown/></D:prop></D:propfind>'
listing = asyncio.run(
	service.propfind(request("PROPFIND", "/", {"Depth": "infinity"}, body), "")
)
assert listing.status == 207
assert isinstance(listing.body, HTTPBodyBlob)
xml = ET.fromstring(listing.body.raw)
hrefs = [item.text for item in xml.findall("{DAV:}response/{DAV:}href")]
assert hrefs == ["/", "/docs/", "/docs/hello%20world.txt", "/empty/"]
assert b"404 Not Found" in listing.body.raw
assert b"secret" not in listing.body.raw

mounted = WebDAVService(backend, prefix="dav")
mountedListing = asyncio.run(
	mounted.propfind(request("PROPFIND", "/dav", {"Depth": "1"}), "")
)
assert b"<D:href>/dav/</D:href>" in mountedListing.body.raw
assert b"<D:href>/dav/docs/</D:href>" in mountedListing.body.raw

invalid = asyncio.run(service.propfind(request("PROPFIND", "/", {"Depth": "2"}), ""))
assert invalid.status == 400

unsafe = '<!DOCTYPE propfind [<!ENTITY xxe "blocked">]><D:propfind xmlns:D="DAV:"><D:allprop/></D:propfind>'
blocked = asyncio.run(
	service.propfind(request("PROPFIND", "/", {"Depth": "0"}, unsafe), "")
)
assert blocked.status == 400

malformed = asyncio.run(
	service.propfind(request("PROPFIND", "/", {"Depth": "0"}, "not xml"), "")
)
assert malformed.status == 400

utf16Unsafe = '<!DOCTYPE propfind [<!ENTITY xxe "blocked">]>'.encode("utf-16")
try:
	service._parseXML(utf16Unsafe)
	assert False
except ValueError:
	pass

limited = WebDAVService(backend, maxDepth=0)
tooDeep = asyncio.run(limited.propfind(request("PROPFIND", "/", {"Depth": "infinity"}), ""))
assert tooDeep.status == 403

writableBackend = MemoryWebDAVBackend({"/source.txt": "source"}, writable=True)
writable = WebDAVService(writableBackend)
assert "PUT" in writable.allow
assert "PROPPATCH" in writable.allow
blocked = asyncio.run(service.put(request("PUT", "/blocked.txt", body="nope"), "blocked.txt"))
assert blocked.status == 405
put = asyncio.run(writable.put(request("PUT", "/new.txt", body="new content"), "new.txt"))
assert put.status == 201
assert asyncio.run(writableBackend.open("/new.txt")) == b"new content"

protected = WebDAVService(
	writableBackend, canWrite=lambda request, path, resource: path != "/protected"
)
assert asyncio.run(
	protected.put(request("PUT", "/protected", body="nope"), "protected")
).status == 403
assert asyncio.run(
	protected.makeCollection(request("MKCOL", "/protected"), "protected")
).status == 403

replace = asyncio.run(
	writable.put(
		request("PUT", "/new.txt", {"If-Match": put.getHeader("Etag") or ""}, "changed"),
		"new.txt",
	)
)
assert replace.status == 204
wildcard = asyncio.run(
	writable.put(
		request("PUT", "/new.txt", {"If-Match": "*"}, "changed again"), "new.txt"
	)
)
assert wildcard.status == 204

collection = asyncio.run(writable.makeCollection(request("MKCOL", "/folder"), "folder"))
assert collection.status == 201
copy = asyncio.run(
	writable.copy(
		request("COPY", "/source.txt", {"Destination": "/folder/copy.txt"}),
		"source.txt",
	)
)
assert copy.status == 201
absoluteCopy = asyncio.run(
	writable.copy(
		request(
			"COPY",
			"/source.txt",
			{"Destination": "HTTP://LOCALHOST/folder/absolute.txt", "Host": "localhost"},
		),
		"source.txt",
	)
)
assert absoluteCopy.status == 201
foreignCopy = asyncio.run(
	writable.copy(
		request(
			"COPY",
			"/source.txt",
			{"Destination": "http://other.test/folder/foreign.txt", "Host": "localhost"},
		),
		"source.txt",
	)
)
assert foreignCopy.status == 400
move = asyncio.run(
	writable.move(
		request("MOVE", "/folder/copy.txt", {"Destination": "/folder/moved.txt"}),
		"folder/copy.txt",
	)
)
assert move.status == 201
assert asyncio.run(writableBackend.open("/folder/moved.txt")) == b"source"

destinationProtected = WebDAVService(
	writableBackend,
	canWrite=lambda request, path, resource: path != "/protected.txt",
)
assert asyncio.run(
	destinationProtected.copy(
		request("COPY", "/source.txt", {"Destination": "/protected.txt"}),
		"source.txt",
	)
).status == 403

noRangesBackend = MemoryWebDAVBackend({"/range.txt": "abcdef"})
noRangesBackend.capabilities = dataclassReplace(noRangesBackend.capabilities, ranges=False)
noRanges = WebDAVService(noRangesBackend)
noRangeResponse = asyncio.run(
	noRanges.read(request("GET", "/range.txt", {"Range": "bytes=1-2"}), "range.txt")
)
assert noRangeResponse.status == 416
assert noRangeResponse.getHeader("Accept-Ranges") is None

proppatchBody = (
	'<propertyupdate xmlns="DAV:"><set><prop>'
	'<displayname>ignored-live-property</displayname>'
	'<x:color xmlns:x="urn:test">blue</x:color>'
	"</prop></set></propertyupdate>"
)
proppatch = asyncio.run(
	writable.proppatch(request("PROPPATCH", "/new.txt", body=proppatchBody), "new.txt")
)
assert proppatch.status == 207
copiedProperties = asyncio.run(
	writable.copy(
		request("COPY", "/new.txt", {"Destination": "/folder/props.txt"}),
		"new.txt",
	)
)
assert copiedProperties.status == 201
copiedListing = asyncio.run(
	writable.propfind(
		request(
			"PROPFIND",
			"/folder/props.txt",
			{"Depth": "0"},
			'<propfind xmlns="DAV:"><prop><x:color xmlns:x="urn:test"/></prop></propfind>',
		),
		"folder/props.txt",
	)
)
assert b">blue<" in copiedListing.body.raw
custom = asyncio.run(
	writable.propfind(
		request(
			"PROPFIND",
			"/new.txt",
			{"Depth": "0"},
			'<propfind xmlns="DAV:"><prop><x:color xmlns:x="urn:test"/></prop></propfind>',
		),
		"new.txt",
	)
)
assert custom.status == 207
assert b">blue<" in custom.body.raw

removed = asyncio.run(writable.remove(request("DELETE", "/new.txt"), "new.txt"))
assert removed.status == 204
assert asyncio.run(writableBackend.stat("/new.txt")) is None

for unsafe in (
	b'<!DOCTYPE propfind><propfind xmlns="DAV:"/>',
	b'<!DOCTYPE propfind [<!ENTITY x SYSTEM "file:///etc/passwd">]><propfind xmlns="DAV:"/>',
	b'<!DOCTYPE propfind [<!ENTITY x "xxxxxxxx">]><propfind xmlns="DAV:">&x;</propfind>',
):
	try:
		service._parseXML(unsafe)
	except ValueError:
		pass
	else:
		raise AssertionError("unsafe XML was accepted")

try:
	service._parseXML(b"<propfind xmlns=\"DAV:\"/>" + b" " * 65_537)
except ValueError:
	pass
else:
	raise AssertionError("oversized XML was accepted")

try:
	service._parseXML(b"\xff")
except ValueError:
	pass
else:
	raise AssertionError("invalid UTF-8 XML was accepted")

# EOF
