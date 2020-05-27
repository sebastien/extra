from ..protocol import Request, Response, WithHeaders
from typing import List,Any,Optional,Union,BinaryIO,Dict
import json

ContentType   = b'content-type'
ContentLength = b'content-length'
Location      = b'location'

# @group(Utility)

def normalizeHeader( header:Union[str,bytes] ):
	return bytes(header.lower().strip(), "utf8")

def unquote( text:bytes ) -> bytes:
	text = text.strip() if text else text
	if not text:
		return text
	if text[0] == text[-1] and text[0] in b"\"'":
		return text[1:-1]
	else:
		return text

class WithHTTPHeaders(WithHeaders):

	# @group(Headers)
	@property
	def contentLength( self ) -> int:
		return int(self.getHeader(ContentType))

	@contentLength.setter
	def contentLength( self, length:int ):
		return self.setHeader(ContentLength, b"%d" % (length))

	@property
	def contentType( self ) -> bytes:
		return self.getHeader(ContentType)

	@contentType.setter
	def contentType( self, value:Union[str,bytes] ):
		return self.setHeader(ContentType, encode(value))

	# @property
	# def userAgent( self ):
	# 	pass

	# @property
	# def range( self ):
	# 	pass

	# @property
	# def compression( self ):
	# 	pass

class HTTPRequest(Request, WithHTTPHeaders):
	POOL:List['HTTPRequest'] = []

	# @group(Responses)
	def __init__( self ):
		super().__init__()
		self.protocol = "http"
		self.protocolVersion = "1.0"
		self.method = "GET"
		self.path   = ""
		self.query:Optional[str]   = None
		self.ip:Optional[str]     = None
		self.port:Optional[int]   = None

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

class HTTPResponse(Response):
	POOL:List['HTTPResponse'] = []

	def fromFile( self ):
		pass

	def fromStream( self ):
		pass


class Parsing:
	"""A collection of functions to process form data."""

	DATA_SPOOL_SIZE = 64 * 1024

	# NOTE: We encountered some problems with the `email` module in Python 3.4,
	# which lead to writing these functions.
	# http://stackoverflow.com/questions/4526273/what-does-enctype-multipart-form-data-mean
	@classmethod
	def ParseMultipart( cls, stream:BinaryIO, contentType:bytes, boundary:bytes, bufferSize=64000 ):
		"""Iterates on a multipart form data file with the given content type. This
		will yield the following couples:

		- `("b", boundary)` when a boundary is found
		- `("h", headers)`  with an map of `header:value` when headers are encountered (header is stripper lowercased)
		- `("d", data)`     with a bytes array of at maximum `bufferSize` bytes.

		"""
		# multipart/form-data
		# assert "multipart/form-data" in contentType or "multipart/mixed" in contentType, "Expected multipart/form-data or multipart/mixed in content type"
		# The contentType is epxected to be
		# >   Content-Type: multipart/form-data; boundary=<BOUNDARY>\r\n
		boundary_length = len(boundary)
		has_more        = True
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
			chunk           = stream.read(read_size)
			chunk_read_size = len(chunk)
			chunk           = rest + chunk
			# If state=="b" it means we've found a boundary at the previous iteration
			# and we need to find the headers
			if state == "b":
				i = chunk.find(b"\r\n\r\n")
				if i >= 0:
					raw_headers:bytes = chunk[:i]
					parsed_headers:Dict[bytes,bytes] = {}
					for line in raw_headers.split(b"\r\n"):
						if not line: continue
						header = line.split(b":",1)
						if len(header) == 2:
							# TODO: We might want to specify an alternate encoding
							name  = normalizeHeader(header[0].decode())
							value = header[1].strip()
							parsed_headers[name] = value
					yield ("h", parsed_headers)
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
	def HeaderValue( cls, text:bytes ) -> Dict[bytes, bytes]:
		"""Parses a header value and returns a dict.

		`multipart/mixed; boundary=inner` will
		return `{b"":b"multipart/mixed", b"boundary"b"inner"}`
		"""
		if not text:
			return {}
		res:Dict[bytes,bytes] = {}
		# We normalize the content-disposition header
		for v in text.split(b";"):
			v = v.strip().split(b"=", 1)
			if len(v) == 1:
				h = b""
				v = unquote(v[0])
			else:
				h = unqute(v[0].strip())
				v = unquote(v[1].strip())
			res[h] = v
		return res

	@classmethod
	def XXXMultipart( cls, file, contentType, bufferSize=64000 ):
		"""Decodes the given multipart data, yielding `(meta, data)`
		couples, where meta is a parsed dict of headers and data
		is a file-like object."""
		is_new       = False
		content_type = None
		disposition  = None
		description  = None
		data_file    = None
		meta         = None
		for state, data in FormData.ParseMultipart(file, contentType):
			if state == "b":
				# We encounter the boundary at the very beginning, or
				# inbetween elements
				if data_file:
					# There might be 2 bytes of data, which will result in
					# meta being None
					if meta is None:
						data_file.close()
					else:
						data_file.seek(0)
						yield (meta, data_file)
				is_new    = True
				data_file = None
				meta      = None
			elif state == "h":
				# The header comes next
				assert is_new
				is_new = False
				if data:
					meta = dict( (h, cls.HeaderValue(v)) for h,v in data.items() )
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
			if meta is None: continue
			disposition = meta["Content-Disposition"]
			# We expect to have a least one of these
			name        = disposition.get("name") or disposition.get("filename") or meta["Content-Description"]
			if name[0] == name[-1] and name[0] in "\"'": name = name[1:-1]
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
	def FormEncoded( self, stream:BinaryIO, charset:Optional[bytes]=None ):
		charset = charset or b'utf8'
		data = stream.read()
		# NOTE: Encoding is not supported yet
		query_params = parse_qs(data)
		# for k,v in list(query_params.items()): self.request._addParam(k,v)


	# NOTE: That's "application/json"
	@classmethod
	def JSON( self, stream:BinaryIO, charset:Optional[bytes]=None ):
		return json.load(stream)

# EOF
