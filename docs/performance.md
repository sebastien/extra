# Performance in Extra

Here are the things that we've done to maximise performance:

-   Use `bytes` instead of `str` so we skip the encoding/decoding at the core
-   Use faster libraries when available (`re2`, `orjson`)
-   Favours zero-copy in parsing (ie. offsets vs values)
-   Request body is lazily loaded and parsed and uses a spool if large.
-   Use of streaming so that data is written directly to output

## Tips

-   Use `bytes` on critical requests to skip the encoding
-   Use dedicated accessors for setting/getting headers, or use the `protocol.http` constants
    for header keys.

## Benchmarking

We run the benchmarks using [NG HTTP/2](https://nghttp2.org/), which is a pretty good and versatile performance
testing suite for both HTTP/1 and HTTP/2.

Here's the one liner to test simple (raw) performance for HTTP/1:

```
h2load  -n100000 -c100 -m10 --h1 http://localhost:8000/
h2load  -n100000 -c100 -m10 --h1 http://localhost:8000/
```

and here's the same for HTTP/2:

```
h2load  -n100000 -c100 -m10 http://localhost:8000/
```

The following reports are done from running the `benchmark_*` scripts
using uvicorn and tests on HTTP/1 using the first `h2load` command:

| Date       |  RPS    | Throughput | Toolkit    |
| ---------- | ------- | ---------- | ---------- |
| 2021-03-21 | 7842.28 |   1.30MB/s | AIOHTTP    |
| 2021-03-21 | 2732.19 | 400.22KB/s | Raw        |
| 2021-03-21 | 2133.21 | 270.82KB/s | Extra      |
| 2021-03-21 | 1873.80 | 259.84KB/s | FastAPI    |
|  |  |  |   |
| 2020-05-28 | 6030.30 | 883.34KB/s | Raw        |
| 2020-05-22 | 5752.87 | 691.02KB/s | Extra+FW   |
| 2020-05-28 | 4850.08 | 615.73KB/s | Extra      |
| 2020-05-28 | 2200.13 | 305.10KB/s | FastAPI    |

## Note: Async impact on latency

The problem with a pure async HTTP server is that any non-async request, or any
async requests that does not yield will simply block other requests. A working
design is then a mix of threads and requests.
