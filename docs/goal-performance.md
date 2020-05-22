# Async impact on latency

The problem with a pure async HTTP server is that any non-async request, or any
async requests that does not yield will simply block other requests. A working
design is then a mix of threads and requests.
