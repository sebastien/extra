# Performance in Extra

Here are the things that we've done to maximise performance:

-   Use `bytes` instead of `str` so we skip the encoding/decoding at the core
-   Use faster libraries when available (`re2`, `orjson`)
-   Favours zero-copy in parsing (ie. offsets vs values)
-   Request body is lazily loaded and parsed and uses a spool if large.

# Benchmarking

We run the benchmarks using [NG HTTP/2](https://nghttp2.org/), which is a pretty good and versatile performance
testing suite for both HTTP/1 and HTTP/2.

Here's the one liner to test simple (raw) performance for HTTP/1:

```
h2load  -n100000 -c100 -m10 --h1 http://localhost:8000/
```

and here's the same for HTTP/2:

```
h2load  -n100000 -c100 -m10 http://localhost:8000/
```

Reports:

-   2020/05/22: 5212.12 req/s, 626.07KB/s [Extra]
-   2020/05/22: 5752.87 req/s, 691.02KB/s [Extra+flyweight]
-   2020/05/22: 6669.87 req/s, 977.03KB/s [Raw]
-   2020/05/28: 4850.08 req/s, 615.73KB/s [Extra:api]
-   2020/05/28: 6030.30 req/s, 883.34KB/s [Extra:raw]
-   2020/05/28: 2200.13 req/s, 305.10KB/s [FastAPI]
