import time
from io import BytesIO
from typing import Optional
from asyncio import StreamReader

"""A reusable mini parser for HTTP that acccumulates data from a bytes
stream."""

# FIXME: Redundant with protocol.http


class HTTPParser:
    """Parses an HTTP request and headers from a stream through the `feed()`
    method."""

    def __init__(
        self, address: str, port: int, stats: Optional[dict[str, float]] = None
    ):
        self.address: str = address
        self.port: int = port
        self.started: float = time.time()
        self.stats: dict[str, float] = stats or {}
        self.reset()

    def reset(self):
        self.method: Optional[str] = None
        self.uri: Optional[str] = None
        self.protocol: Optional[str] = None
        self.headers: dict[str, str] = {}
        self.step: int = 0
        self.rest: Optional[bytes] = None
        self.status: int = 0
        self._stream: Optional[StreamReader] = None
        self.started = 0.0

    def setInput(self, stream: StreamReader):
        self._stream = stream
        return self

    def feed(self, data: bytes) -> bool:
        """Feeds data into the context, returning False as soon as we're
        past reading the body"""
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
                assert o <= j
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
            assert i >= 0
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
            self.method = line[:j].decode()
            self.uri = line[j + 1 : k].decode()
            self.protocol = line[k + 1 :].decode()
            step = 1
        elif not line:
            # That's an EMPTY line, probably the one separating the body
            # from the headers
            step += 1
        elif step >= 1:
            # That's a HEADER line
            step = 1
            j = line.index(b":")
            h = line[:j].decode().strip()
            j += 1
            if j < len(line) and line[j] == " ":
                j += 1
            v = line[j:].decode().strip()
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
                    # FIXME: Somehow when returning directly there
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
                return rest + (
                    (await self._stream.read(size - len(rest))) if self._stream else b""
                )

    def asDict(self):
        """Exports a JSONable representation of the context."""
        return {
            "method": self.method,
            "uri": self.uri,
            "protocol": self.protocol,
            "headers": [(k, v) for k, v in self.headers.items()],
        }


# EOF
