# Performance in Extra

Here are the things that we've done to maximise performance:

-   Use `bytes` instead of `str` so we skip the encoding/decoding at the core
-   Use faster libraries when available (`re2`, `orjson`)
-   Favours zero-copy in parsing (ie. offsets vs values)
-   Request body is lazily loaded and parsed and uses a spool if large.
-   Use of streaming so that data is written directly to output

## Keep-Alive

HTTP/1.0 (used by tools like `ab`) closes connection at the end of each
request, while

## Tips

-   Use `bytes` on critical requests to skip the encoding
-   Use dedicated accessors for setting/getting headers, or use the `protocol.http` constants
    for header keys.

## Benchmarking

We run the benchmarks using [NG HTTP/2](https://nghttp2.org/), which is a pretty good and versatile performance
testing suite for both HTTP/1 and HTTP/2.

Here's the one liner to test simple (raw) performance for HTTP/1.1:

```
h2load  -n10000 -c1000 -m1 --h1 http://localhost:8000/
```

Note that using `-m10` for instance enables HTTP pipelining.

and here's the same for HTTP/1.0:

```
ab -n10000 -c1000 http://localhost:8000
```




The problem with a pure async HTTP server is that any non-async request, or any
async requests that does not yield will simply block other requests. A working
design is then a mix of threads and requests.
