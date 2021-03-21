import asyncio
# FROM: https://github.com/oberstet/scratchbox/blob/master/python/asyncio/tcp_echo_server.py


class HTTPServer(asyncio.Protocol):

    def connection_made(self, transport):
        pass
        self.transport = transport

    def connection_lost(self, transport):
        pass

    def eof_received(self):
        pass

    def data_received(self, data):
        self.transport.write(
            b"HTTP/1.0 200 NA\r\nContent-Type: text/plain\r\nContent-Length: 4\r\n\r\n12345")
        self.transport.write_eof()


if __name__ == '__main__':
    loop = asyncio.get_event_loop()

    f = loop.create_server(HTTPServer, port=8000, backlog=100_000)
    server = loop.run_until_complete(f)
    try:
        loop.run_forever()
    finally:
        server.close()
        loop.close()
