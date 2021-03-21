from ..protocol import Request, Response, Headers, asBytes
from typing import List, Any, Optional, Union, BinaryIO, Dict, Iterable, Tuple
from tempfile import SpooledTemporaryFile
from extra.util import unquote, Flyweight
from urllib.parse import parse_qs
import io
# TODO: Support faster encoders
import json
import tempfile
import collections


# 8Mib spool size
SPOOL_MAX_SIZE = 8 * 1024 * 1024
BUFFER_MAX_SIZE = 1 * 1024 * 1024

Range = Tuple[int, int]
ContentType = b'content-type'
ContentLength = b'content-length'
ContentDisposition = b'content-disposition'
ContentDescription = b'content-description'
Location = b'location'

# FIXME: This should be a stream writer


def asJSON(value):
    return bytes(json.dumps(value), "utf8")

# @property
# def userAgent( self ):
#     pass

# @property
# def range( self ):
#     pass

# @property
# def compression( self ):
#     pass


class WithHeaders:

    def __init__(self):
        self.headers = Headers()

    def reset(self):
        self.headers.reset()


class HTTPRequest(Request, WithHeaders):
    POOL: List['HTTPRequest'] = []

    def __init__(self):
        super().__init__()
        WithHeaders.__init__(self)
        self.protocol: Optional[str] = None
        self.protocolVersion: Optional[str] = None
        self.method: Optional[str] = None
        self.path: Optional[str] = None
        self.query: Optional[str] = None
        self.ip: Optional[str] = None
        self.port: Optional[int] = None
        self._body: Optional[Body] = None
        self._reader = None
        self._readCount = 0
        self._hasMore = True

    @property
    def isInitialized(self):
        return self.method != None and self.path != None

    # @group(Flyweight)

    def init(self, reader):
        super().init()
        self._reader = reader
        self._readCount = 0
        self._hasMore = True
        self._body = None
        return self

    def reset(self):
        super().reset()
        WithHeaders.reset(self)
        self._body = self._body.reset() if self._body else None
        return self

    # @group(Loading)

    async def read(self, count: int = -1) -> Optional[bytes]:
        """Only use read if you want to acces the raw data in chunks."""
        if self._hasMore:
            has_more, data = await self._reader(count)
            self._hasMore = bool(has_more)
            self._readCount += len(data)
            return data
        else:
            return None

    async def load(self):
        """Loads all the data and returns a list of bodies."""
        body = self.body
        while True:
            chunk = await self.read()
            if chunk is not None:
                body.feed(chunk)
            else:
                break
        try:
            content_length = int(
                self.contentLength) if self.contentLength else None
        except ValueError as e:
            # There might be a wrong encoding, in which case the request is
            # probably malformed.
            content_length = None
        body.setLoaded(self.contentType, content_length)
        return self

    @property
    def body(self) -> 'Body':
        if not self._body:
            self._body = Body.Create()
        return self._body

    # @group(Headers)
    @property
    def contentLength(self) -> int:
        return int(self.headers.get(ContentType))

    def setContentLength(self, length: int):
        self.headers.set(ContentLength, b"%d" % (length))
        return self

    @property
    def contentType(self) -> bytes:
        return self.headers.get(ContentType)

    def setContentType(self, value: Union[str, bytes]):
        self.headers.set(ContentType, asBytes(value))
        return self

    def setHeader(self, name: Union[str, bytes], value: Union[str, bytes]):
        self.headers.set(name, value)
        return self

    def getHeader(self, name: Union[str, bytes]):
        return self.headers.get(name)

    # @group(Responses)

    def returns(self, value: Any, contentType: Optional[Union[str, bytes]] = b"application/json", status: int = 200):
        # FIXME: This should be a stream writer
        return HTTPResponse.Create().init(status).setContent(asJSON(value), contentType)

    def respond(self, value: Any, contentType: Optional[Union[str, bytes]] = None, status: int = 200):
        return HTTPResponse.Create().init(status).setContent(value, contentType)

    def redirect(self, url, content: Optional[Union[str, bytes]] = None, contentType=b"text/plain", permanent=False):
        """Responds to this request by a redirection to the following URL"""
        return self.respond(content, contentType, status=301 if permanent else 302).setHeader(Location, url)

    def respondFile(self):
        return HTTPResponse.Create().init(200).fromFile()

    def respondStream(self):
        return HTTPResponse.Create().init(200).fromStream()

    # @group(Errors)

    def notFound(self) -> 'HTTPResponse':
        return HTTPResponse.Create().init(status=404).setContent("Resource not found")


class HTTPResponse(Response, WithHeaders):
    POOL: List['HTTPResponse'] = []

    def __init__(self):
        super().__init__()
        WithHeaders.__init__(self)

    def fromFile(self):
        pass

    def fromStream(self):
        pass

# -----------------------------------------------------------------------------
#
# BODY
#
# -----------------------------------------------------------------------------

# @note We need to keep this separate


class Body(Flyweight):

    POOL: List['Body'] = []
    UNDEFINED = "undefined"
    RAW = "raw"
    MULTIPART = "multipart"
    JSON = "json"

    def __init__(self, isShort=False):
        self.spool: Optional[Union[io.BytesIO,
                                   tempfile.SpooledTemporaryFile]] = None
        self.isShort = isShort
        self.isLoaded = False
        self.contentType: Optional[bytes] = None
        self.contentLength: Optional[bytes] = None
        #self.next:Optional[Body] = None
        self._type = Body.UNDEFINED
        self._raw: Optional[bytes] = None
        self._value: Any = None

    @property
    def raw(self) -> bytes:
        # We don't need the body to be fully loaded
        if self._raw == None:
            self.spool.seek(0)
            self._raw = self.spool.read()
        return self._raw

    @property
    def value(self) -> Any:
        if not self.isLoaded:
            raise Exception(
                "Body is not loaded, 'await request.load()' required")
        if not self._value:
            self.process()
        return self._value

    def reset(self):
        if isinstance(self.spool, io.BytesIO):
            pass
        elif isinstance(self.spool, tempfile.SpooledTemporaryFile):
            pass
        self.spool = None
        self.isLoaded = False
        self.contentType = None
        self.contentLength = None
        self._raw = None
        self._value = None
        return self

    def setLoaded(self, contentType: bytes, contentLength: Optional[int]):
        """Sets the body as loaded. It is then ready to be decoded and its
        value field will become accessible."""
        self.contentType = contentType
        self.contentLength = contentLength
        self.isLoaded = True
        return self

    def feed(self, data: bytes):
        """Feeds data to the body's spool"""
        # We lazily create the spool
        if not self.spool:
            content_length = self.contentLength
            is_short = content_length and content_length <= BUFFER_MAX_SIZE
            self.spool = io.BytesIO() if is_short else tempfile.SpooledTemporaryFile(
                max_size=SPOOL_MAX_SIZE)
        self.spool.write(data)
        # We invalidate the cache
        self._raw = None
        self._value = None
        return self

    def process(self):
        parsed_content = Parse.HeaderValue(self.contentType)
        content_type = parsed_content.get(b"")
        print("PARSE CONTENT", parsed_content)
        if content_type == b"multipart/form-data":
            self.spool.seek(0)
            for headers, data_file in Decode.Multipart(self.spool, parsed_content[b'boundary']):
                print(headers, data_file)
        else:
            return None

# -----------------------------------------------------------------------------
#
# PARSE
#
# -----------------------------------------------------------------------------


# TODO: Should merge in the util.http stuff as well
class Parse:
    """A collection of parsing functions used to extract data from HTTP
    binary payloads."""

    # @tag(low-level)
    @classmethod
    def HeaderOffsets(cls, data: bytes, start: int = 0, end: int = -1) -> Iterable[Tuple[Range, Range]]:
        """Parses the headers encoded in the `data` from the given `start` offset to the
        given `end` offset."""
        end: int = len(data) - 1 if end < 0 else min(len(data) - 1, end)
        offset: int = start
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
                header_end = next_colon
                value_start = next_colon + 1
                value_end = next_eol
                yield ((header_start, header_end), (value_start, value_end))
            # We update the cursor
            offset = next_eol

    @classmethod
    def Header(cls, data: bytes, offset: int = 0, end: int = -1) -> Iterable[Tuple[Range, Range]]:
        """A wrapper around `HeaderOffsets` that yields slices of the bytes instead of the
        offsets."""
        for (hs, he), (vs, ve) in Parse.HeaderOffsets(data, offset, end):
            yield (data[hs:he], data[vs:ve])

    @classmethod
    def HeaderValueOffsets(cls, data: bytes, start: int = 0, end: int = -1) -> Iterable[Tuple[int, int, int, int]]:
        """Parses a header value and returns an iterator of offsets for name and value
        in the `data`.

        `multipart/mixed; boundary=inner` will
        return `{b"":b"multipart/mixed", b"boundary":b"inner"}`
        """
        end: int = len(data) - 1 if end < 0 else min(len(data) - 1, end)
        result: Dict[bytes, bytes] = {}
        offset: int = start
        while offset < end:
            # The next semicolumn is the next separator
            field_end: int = data.find(b";", offset)
            if field_end == -1:
                field_end = end
            value_separator: int = data.find(b"=", offset, field_end)
            if value_separator == -1:
                name_start, name_end = offset, offset
                value_start, value_end = offset, field_end
            else:
                name_start, name_end = offset, value_separator
                value_start, value_end = value_separator + 1, field_end
            # We strip everything -- 32 == space in ASCII
            while name_start < name_end and data[name_start] == 32:
                name_start += 1
            while name_start < name_end and data[name_end] == 32:
                name_end -= 1
            while value_start < value_end and data[value_start] == 32:
                value_start += 1
            while value_start < value_end and data[value_end] == 32:
                value_end -= 1
            yield name_start, name_end, value_start, value_end
            offset = field_end + 1

    @classmethod
    def HeaderValue(cls, data: bytes, start: int = 0, end: int = -1) -> Dict[bytes, bytes]:
        return dict((data[ks:ke], data[vs:ve]) for ks, ke, vs, ve in Parse.HeaderValueOffsets(data, start, end))

# -----------------------------------------------------------------------------
#
# DECODE
#
# -----------------------------------------------------------------------------


class Decode:
    """A collection of functions to process form data."""

    # NOTE: We encountered some problems with the `email` module in Python 3.4,
    # which lead to writing these functions.
    # http://stackoverflow.com/questions/4526273/what-does-enctype-multipart-form-data-mean
    @classmethod
    def MultipartChunks(cls, stream: BinaryIO, boundary: bytes, bufferSize=1024*1024) -> Iterable[Tuple[str, Any]]:
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
        has_more = True
        # FIXME: We should keep indexes instead of copying all the time, this
        # is a big problem.
        rest = b""
        read_size = bufferSize + boundary_length
        state = None
        # We want this implementation to be efficient and stream the data, which
        # is especially important when large files (imagine uploading a video)
        # are processed.
        while has_more:
            # Here we read bufferSize + boundary_length, and will return at
            # maximum bufferSize bytes per iteration. This ensure that if
            # the read stop somewhere within a boundary we'll stil be able
            # to find it at the next iteration.
            chunk = stream.read(read_size)
            chunk_read_size = len(chunk)
            chunk = rest + chunk
            # If state=="b" it means we've found a boundary at the previous iteration
            # and we need to find the headers
            if state == "b":
                i = chunk.find(b"\r\n\r\n")
                if i >= 0:
                    # FIXME: Should really yield offsets
                    raw_headers: bytes = chunk[:i]
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
    def Multipart(cls, stream: BinaryIO, boundary: bytes, bufferSize=64000) -> Iterable[Tuple[Headers, bytes]]:
        """Decodes the given multipart data, yielding `(meta, data)`
        couples, where meta is a parsed dict of headers and data
        is a file-like object."""
        is_new = False
        spool: Optional[SpooledTemporaryFile] = None
        headers: Optional[Headers] = None
        for state, data in Decode.MultipartChunks(stream, boundary):
            if state == "b":
                # We encounter the boundary at the very beginning, or
                # inbetween elements. If we don't have a daa
                if spool:
                    # There might be 2 bytes of data, which will result in
                    # meta being None
                    # TODO: Not sure when/why this happens, should have
                    # a test case.
                    if headers is None:
                        spool.close()
                    else:
                        spool.seek(0)
                        yield (headers, spool)
                is_new = True
                spool = None
                headers = None
            elif state == "h":
                # The header comes next
                assert is_new
                is_new = False
                if data:
                    print("HEADERS", data)
                    headers = Headers.FromItems(data.items())
                else:
                    headers = None
            elif state == "d":
                assert not is_new
                if not spool:
                    spool = tempfile.SpooledTemporaryFile(
                        max_size=SPOOL_MAX_SIZE)
                spool.write(data)
            else:
                raise Exception("State not recognized: {0}".format(state))
        if spool:
            spool.seek(0)
            yield (headers, spool)

    # @classmethod
    # def Multipart( self, stream:BinaryIO, boundary:bytes ):
    #     # We're using the FormData
    #     # FIXME: This assumes headers are Camel-Case
    #     for meta, data in FormData.DecodeMultipart(dataFile, boundary):
    #         # There is sometimes leading and trailing data (not sure
    #         # exaclty why, but try the UploadModule example) to see
    #         # with sample payloads.
    #         if meta is None:
    #             continue
    #         disposition = meta["Content-Disposition"]
    #         # We expect to have a least one of these
    #         name = disposition.get("name") or disposition.get("filename") or meta["Content-Description"]
    #         if name[0] == name[-1] and name[0] in "\"'":
    #             name = name[1:-1]
    #         if "filename" in disposition:
    #             # NOTE: This stores the whole data in memory, we don't want
    #             # that.
    #             new_file= File(
    #                 # FIXME: Shouldnot use read here
    #                 data        = data.read(),
    #                 contentType = meta["Content-Type"][""],
    #                 name        = name,
    #                 filename    = disposition.get("filename") or meta["Content-Description"]
    #             )
    #             self.request._addFile (name, new_file)
    #             self.request._addParam(name, new_file)
    #         else:
    #             self.request._addParam(name, name)

    # NOTE: That's "application/x-www-form-urlencoded"
    @classmethod
    async def FormEncoded(self, stream: BinaryIO, charset: Optional[bytes] = None) -> Dict[str, List[str]]:
        return parse_qs(stream.read())

# -----------------------------------------------------------------------------
#
# HTTP PARSER
#
# -----------------------------------------------------------------------------


# FIXME: Make Flyweight
class HTTPParser:
    """Parses an HTTP request and headers from a stream through the `feed()`
    method."""

    def __init__(self, address: str, port: int, stats: Optional[dict]):
        self.address = address
        self.port = port
        self.stats = stats
        self.reset()

    def reset(self):
        self.method = None
        self.uri = None
        self.protocol = None
        self.headers = collections.OrderedDict()
        self.step = 0
        self.rest = None
        self.status = None
        self._stream = None

    def input(self, stream):
        self._stream = stream
        return self

    def feed(self, data: bytes):
        """Feeds data into the context."""
        if self.step >= 2:
            # If we're past reading the body (>=2), then we can't decode anything
            return False
        else:
            t = self.rest + data if self.rest else data
            # TODO: We're looking for the final \r\n\r\n that separates
            # the header from the body.
            i = t.find(b"\r\n\r\n")
            if i == -1:
                self.rest = t
            else:
                # We skip the 4 bytes of \r\n\r\n
                j = i + 4
                o = self._parseChunk(t, 0, j)
                assert (o <= j)
                self.rest = t[j:] if j < len(t) else None
            return True

    def _parseChunk(self, data, start, end):
        """Parses a chunk of the data, which MUST have at least one
        /r/n in there and end with /r/n."""
        # NOTE: In essence, this is pretty close to data[stat:end].split("\r\n")
        # 0 = REQUEST
        # 1 = HEADERS
        # 2 = BODY
        # 3 = DONE
        step = self.step
        o = start
        l = end
        # We'll stop once we reach the end passed above.
        while step < 2 and o < l:
            # We find the closest line separators. We're guaranteed to
            # find at least one.
            i = data.find(b"\r\n", o)
            # The chunk must have \r\n at the end
            assert (i >= 0)
            # Now we have a line, so we parse it
            step = self._parseLine(step, data[o:i])
            # And we increase the offset
            o = i + 2
        # We update the state
        self.step = step
        return o

    def _parseLine(self, step: int, line: bytes):
        """Parses a line (without the ending `\r\n`), updating the
        context's {method,uri,protocol,headers,step} accordingly. This
        will stop once two empty lines have been encountered."""
        if step == 0:
            # That's the REQUEST line
            j = line.index(b" ")
            k = line.index(b" ", j + 1)
            self.method = line[:j]
            self.uri = line[j+1:k]
            self.protocol = line[k+1:]
            step = 1
        elif not line:
            # That's an EMPTY line, probably the one separating the body
            # from the headers
            step += 1
        elif step >= 1:
            # That's a HEADER line
            step = 1
            j = line.index(b":")
            h = line[:j].strip()
            j += 1
            if j < len(line) and line[j] == " ":
                j += 1
            v = line[j:].strip()
            self.headers[h] = v
        return step

    # TODO: We might want to move that to connection, but right
    # now the HTTP context is a better fix.
    # variant of that.
    async def read(self, size=None) -> Optional[bytes]:
        """Reads `size` bytes from the context's input stream, using
        whatever data is left from the previous data feeding."""
        assert size != 0
        rest = self.rest
        # This method is a little bit contrived because e need to test
        # for all the cases. Also, this needs to be relatively fast as
        # it's going to be used often.
        if rest is None:
            if self._stream:
                if size is None:
                    res = await self._stream.read()
                    return res
                else:
                    # FIXME: Somewhow when returning directly there
                    # is an issue when receiving large uploaded files, it
                    # will block forever.
                    res = await self._stream.read(size)
                    return res
            else:
                return b""
        else:
            self.rest = None
            if size is None:
                if self._stream:
                    return rest + (await self._stream.read())
                else:
                    return rest
            elif len(rest) > size:
                self.rest = rest[size:]
                return rest[:size]
            else:
                return rest + (await self._stream.read(size - len(rest)))

    def export(self):
        """Exports a JSONable representation of the context."""
        return {
            "method": self.method,
            "uri": self.uri,
            "protocol": self.protocol,
            "headers": [(k, v) for k, v in self.headers.items()],
        }


# EOF
