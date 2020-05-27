# Performance Testing

[NG HTTP/2](https://nghttp2.org/) is pretty good and versatile performance
testing suite for both HTTP/1 and HTTP/2. Here's a simple test suite:

Libraries:

-   re2 instead of re
-   orjson instead of json

```
# HTTP/1 Testing
h2load  -n100000 -c100 -m10 --h1 http://localhost:8000/

-  2020/05/22: 5212.12 req/s, 626.07KB/s [Extra]
-  2020/05/22: 5752.87 req/s, 691.02KB/s [Extra+flyweight]
-  2020/05/22: 6669.87 req/s, 977.03KB/s [Raw]

# HTTP/2 Testing
h2load  -n100000 -c100 -m10 http://localhost:8000/
```

2020/05/28:

-   4850.08 req/s, 615.73KB/s [Extra:api]
-   6030.30 req/s, 883.34KB/s [Extra:raw]
-   2200.13 req/s, 305.10KB/s [FastAPI]

Todo:
