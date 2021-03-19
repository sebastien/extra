from extra import Service
from extra.io import Channel, consume
import time
import threading


def producer(channel: Channel):
    """A timer that streams value every second."""
    while channel.isOpen:
        channel.put(time.time())
        time.sleep(1)


class API(Service):

    def __init__(self, channel: Channel):
        super().__init__()
        self.channel: Optional[Channel] = None
        self.thread: Optional[Thread] = None

    def start(self):
        self.channel = Channel().open()
        self.thread = threading.Thread(target=producer, args=(self.channel,))
        self.thread.start()

    def stop(self):
        self.channel.close()
        self.thread.stop()

    # @p Using `expose` automatically exposes the method through the web
    # service, encoding the results as JSON
    @expose(GET="time")
    # TODO:We should have encode
    async def time(self):
        for value in await consume(self.channel):
            yield value


# NOTE: You can start this with `uvicorn workers:app`
app = serve(API)
# EOF
