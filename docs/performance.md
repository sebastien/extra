# Performance Testing

[NG HTTP/2](https://nghttp2.org/) is pretty good and versatile performance
testing suite for both HTTP/1 and HTTP/2. Here's a simple test suite:

```
# HTTP/1 Testing
h2load  -n100000 -c100 -m10 --h1 http://localhost:8000/

# HTTP/2 Testing
h2load  -n100000 -c100 -m10 http://localhost:8000/
```
