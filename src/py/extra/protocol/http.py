from ..protocol import Request, Response, Headers, Body
from typing import List,Any,Optional,Union,BinaryIO,Dict,Iterable,Tuple
from tempfile import SpooledTemporaryFile
from extra.util import unquote, Flyweight
from urllib.parse import parse_qs
# TODO: Suport faster JSON libs
import json

# 8Mib spool size
SPOOL_MAX_SIZE = 8 * 1024 * 1024

Range = Tuple[int,int]
ContentType        = b'content-type'
ContentLength      = b'content-length'
ContentDisposition = b'content-disposition'
ContentDescription = b'content-description'
Location           = b'location'

# @property
# def userAgent( self ):
# 	pass

# @property
# def range( self ):
# 	pass

# @property
# def compression( self ):
# 	pass

class WithHeaders:

	def __init__( self ):
		self.headers = Headers()

	def reset( self ):
		self.headers.reset()

class HTTPRequest(Request, WithHeaders):
	POOL:List['HTTPRequest'] = []

	def __init__( self ):
		super().__init__()
		WithHeaders.__init__(self)
		self.protocol = "http"
		self.protocolVersion = "1.0"
		self.method = "GET"
		self.path   = ""
		self.query:Optional[str]   = None
		self.ip:Optional[str]     = None
		self.port:Optional[int]   = None
		self._bodies:List[Body] = []
		self._reader = None
		self._readCount = 0
		self._hasMore = True

	# @group(Flyweight)

	def init( self, reader ):
		super().init()
		self._reader = reader
		self._readCount = 0
		self._hasMore = True
		return self

	def reset( self ):
		super().reset()
		WithHeaders.reset(self)
		while self._bodies:
			self._bodies.pop().recycle()
		return self

	# @group(Loading)

	async def read( self, count:int=-1 ) -> Optional[bytes]:
		"""Only use read if you want to acces the raw data in chunks."""
		if self._hasMore:
			has_more, data = await self._reader(count)
			self._hasMore = bool(has_more)
			self._readCount += len(data)
			return data
		else:
			return None


	def load( self ):
		"""Loads all the data and returns a list of bodies."""
		return self

	@property
	def body( self ) -> Optional[Body]:
		return self.body[0] if self.body else 0

	# @group(Headers)
	@property
	def contentLength( self ) -> int:
		return int(self.headers.get(ContentType))

	def setContentLength( self, length:int ):
		self.headers.set(ContentLength, b"%d" % (length))
		return self

	@property
	def contentType( self ) -> bytes:
		return self.headers.get(ContentType)

	def setContentType( self, value:Union[str,bytes] ):
		self.headers.set(ContentType, encode(value))
		return self

	def setHeader( self, name:Union[str,bytes], value:Union[str,bytes] ):
		self.headers.set(name, value)
		return self

	def getHeader( self, name:Union[str,bytes] ):
		return self.headers.get(name)

	# @group(Responses)

	def respond( self, value:Any, contentType:Optional[Union[str,bytes]]=None, status:int=200 ):
		return HTTPResponse.Create().init(status).setContent(value, contentType)

	def redirect( self, url, content:Optional[Union[str,bytes]]=None, contentType=b"text/plain", permanent=False ):
		"""Responds to this request by a redirection to the following URL"""
		return self.respond(content, contentType, status=301 if permanent else 302).setHeader(Location, url)

	def respondFile( self ):
		return HTTPResponse.Create().init(200).fromFile()

	def respondStream( self ):
		return HTTPResponse.Create().init(200).fromStream()

	# @group(Errors)

	def notFound( self ) -> 'HTTPResponse':
		return HTTPResponse.Create().init(status=404).setContent("Resource not found")

class HTTPResponse(Response, WithHeaders):
	POOL:List['HTTPResponse'] = []

	def __init__( self ):
		super().__init__()
		WithHeaders.__init__(self)

	def fromFile( self ):
		pass

	def fromStream( self ):
		pass

# -----------------------------------------------------------------------------
#
# BODY
#
# -----------------------------------------------------------------------------

# @note We need to keep this separate
class Body:

	def ___init__( self, isShort=False ):
		self.spool = io.IOString() if isShort else tempfile.SpooledTemporaryFile(max_size=cls.DATA_SPOOL_SIZE)
		self.isShort = isShort

	def cleanup( self ):
		if self.isShort:
			# Cleanup the string IO
			pass
		else:
			# TODO: Cleanup the spool file
			pass


	def feed( self, data:bytes ):
		"""Feeds data to the body's spool"""
		spool.write(data)
		return self

	def process( self, contentType:bytes ):



# -----------------------------------------------------------------------------
#
# PARSE
#
# -----------------------------------------------------------------------------

class Parse:
	"""A collection of parsing functions used to extract data from HTTP
	binary payloads."""

	# @tag(low-level)
	@classmethod
	def HeaderOffsets( cls, data:bytes, start:int=0, end:int=-1 ) -> Iterable[Tuple[Range,Range]]:
		"""Parses the headers encoded in the `data` from the given `start` offset to the
		given `end` offset."""
		end:int = len(data) - 1 if end < 0 else min(len(data) - 1, end)
		offset:int = start
		while offset < end:
			next_eol = data.find(b"\r\n", offset)
			# If we don't find an EOL, we're reaching the end of the data
			if next_eol == -1:
				next_eol = end
			# Now we look for the value separator
			next_colon = data.find(b":", offset, end)
			# If we don't find a header, there's nothing we can do
			if next_colon == -1:
				continue
			else:
				header_start = offset
				header_end   = next_colon
				value_start  = next_colon + 1
				value_end    = next_eol
				yield ((header_start, header_end), (value_start, value_end))
			# We update the cursor
			offset = next_eol

	@classmethod
	def Header( cls, data:bytes, offset:int=0, end:int=-1 ) -> Iterable[Tuple[Range,Range]]:
		"""A wrapper around `HeaderOffsets` that yields slices of the bytes instead of the
		offsets."""
		for (hs,he),(vs,ve) in Parse.HeaderOffsets(data, offset, end):
			yield (data[hs:he], data[vs:ve])

	@classmethod
	def HeaderValueOffsets( cls, data:bytes, start:int=0, end:int=-1 ) -> Iterable[Tuple[int,int,int,int]]:
		"""Parses a header value and returns an iteartor of offsets for name and value
		in the `data`.

		`multipart/mixed; boundary=inner` will
		return `{b"":b"multipart/mixed", b"boundary":b"inner"}`
		"""
		end:int = len(data) - 1 if end < 0 else min(len(data) - 1, end)
		result:Dict[bytes,bytes] = {}
		offset:int = start
		while offset < end:
			# The next semicolumn is the next separator
			field_end:int = data.find(b";", offset)
			if field_end == -1:
				field_end = end
			value_separator:int = data.find(b"=", offset, field_end)
			if value_separator == -1:
				name_start, name_end = offset, offset
				value_start, value_end = offset, field_end
			else:
				name_start, name_end = offset, value_separator
				value_start, value_end = value_separator + 1, field_end
			# We strip everything
			while name_start < name_end and name_start == b' ': name_start += 1
			while name_start < name_end and name_end == b' ': name_end -= 1
			while value_start < value_end and value_start == b' ': value_start += 1
			while value_start < value_end and value_end == b' ': value_end -= 1
			yield name_start, name_end, value_start, value_end

	@classmethod
	def HeaderValue( cls, data:bytes, start:int=0, end:int=-1 ) -> Dict[bytes,bytes]:
		return dict((data[ks:ke],data[vs:ve]) for ks,ke,vs,ve in Parse.HeaderValueOffsets(data, start, end))

# -----------------------------------------------------------------------------
#
# DECODE
#
# -----------------------------------------------------------------------------

class Decode:
	"""A collection of functions to process form data."""

	DATA_SPOOL_SIZE = 64 * 1024

	# NOTE: We encountered some problems with the `email` module in Python 3.4,
	# which lead to writing these functions.
	# http://stackoverflow.com/questions/4526273/what-does-enctype-multipart-form-data-mean
	@classmethod
	async def MultipartChunks( cls, stream:BinaryIO, boundary:bytes, bufferSize=1024*1024 ) -> Iterable[Tuple[str,Any]]:
		"""Iterates on a multipart form data file with the given `boundary`, reading `bufferSize` bytes
		for each iteration. This will yield tuples matching what was parsed, like so:

		- `("b", boundary)` when a boundary is found
		- `("h", headers)`  with an map of `header:value` when headers are encountered (header is stripper lowercased)
		- `("d", data)`     with a bytes array of at maximum `bufferSize` bytes.

		Note that this is a low-level method.
		"""
		# multipart/form-data
		# assert "multipart/form-data" in contentType or "multipart/mixed" in contentType, "Expected multipart/form-data or multipart/mixed in content type"
		# The contentType is epxected to be
		# >   Content-Type: multipart/form-data; boundary=<BOUNDARY>\r\n
		boundary_length = len(boundary)
		has_more        = True
		# FIXME: We should keep indexes instead of copying all the time, this
		# is a big problem.
		rest            = b""
		read_size       = bufferSize + boundary_length
		state           = None
		# We want this implementation to be efficient and stream the data, which
		# is especially important when large files (imagine uploading a video)
		# are processed.
		while has_more:
			# Here we read bufferSize + boundary_length, and will return at
			# maximum bufferSize bytes per iteration. This ensure that if
			# the read stop somewhere within a boundary we'll stil be able
			# to find it at the next iteration.
			chunk           = await stream.read(read_size)
			chunk_read_size = len(chunk)
			chunk           = rest + chunk
			# If state=="b" it means we've found a boundary at the previous iteration
			# and we need to find the headers
			if state == "b":
				i = chunk.find(b"\r\n\r\n")
				if i >= 0:
					# FIXME: Should really yield offsets
					raw_headers:bytes = chunk[:i]
					yield ("h", raw_headers)
					chunk = chunk[i+4:]
				else:
					yield ("h", None)
			# Now we look for the next boundary
			i = chunk.find(boundary)
			if i == -1:
				yield ("d", chunk[0:bufferSize])
				rest = chunk[bufferSize:]
				state = "d"
			else:
				# The body will end with \r\n + boundary
				if i > 2:
					yield ("d", chunk[0:i - 2])
				rest = chunk[i+boundary_length:]
				yield ("b", boundary)
				state = "b"
			has_more = len(chunk) > 0 or len(chunk) == read_size

	@classmethod
	async def Multipart( cls, stream:BinaryIO, boundary:bytes, bufferSize=64000 ) -> Iterable[Tuple[Headers,bytes]]:
		"""Decodes the given multipart data, yielding `(meta, data)`
		couples, where meta is a parsed dict of headers and data
		is a file-like object."""
		is_new       = False
		spool:Optional[SpooledTemporaryFile] = None
		headers:Optional[Headers] = None
		for state, data in await Decode.MultipartChunks(stream, boundary):
			if state == "b":
				# We encounter the boundary at the very beginning, or
				# inbetween elements. If we don't have a daa
				if data_file:
					# There might be 2 bytes of data, which will result in
					# meta being None
					# TODO: Not sure when/why this happens, should have
					# a test case.
					if headers is None:
						data_file.close()
					else:
						data_file.seek(0)
						yield (headers, data_file)
				is_new    = True
				data_file = None
				headers      = None
			elif state == "h":
				# The header comes next
				assert is_new
				is_new = False
				if data:
					headers = Headers.FromItems(data.items())
				else:
					meta = None
			elif state == "d":
				assert not is_new
				if not data_file:
					data_file = tempfile.SpooledTemporaryFile(max_size=cls.DATA_SPOOL_SIZE)
				data_file.write(data)
			else:
				raise Exception("State not recognized: {0}".format(state))
		if data_file:
			data_file.seek(0)
			yield (meta, data_file)

	@classmethod
	def Multipart( self, stream:BinaryIO ):
		# We're using the FormData
		# FIXME: This assumes headers are Camel-Case
		for meta, data in FormData.DecodeMultipart(dataFile, content_type):
			# There is sometimes leading and trailing data (not sure
			# exaclty why, but try the UploadModule example) to see
			# with sample payloads.
			if meta is None:
				continue
			disposition = meta["Content-Disposition"]
			# We expect to have a least one of these
			name = disposition.get("name") or disposition.get("filename") or meta["Content-Description"]
			if name[0] == name[-1] and name[0] in "\"'":
				name = name[1:-1]
			if "filename" in disposition:
				# NOTE: This stores the whole data in memory, we don't want
				# that.
				new_file= File(
					# FIXME: Shouldnot use read here
					data        = data.read(),
					contentType = meta["Content-Type"][""],
					name        = name,
					filename    = disposition.get("filename") or meta["Content-Description"]
				)
				self.request._addFile (name, new_file)
				self.request._addParam(name, new_file)
			else:
				self.request._addParam(name, name)

	# NOTE: That's "application/x-www-form-urlencoded"
	@classmethod
	async def FormEncoded( self, stream:BinaryIO, charset:Optional[bytes]=None ) -> Dict[str,List[str]]:
		return  parse_qs(stream.read())

# EOF
