# Performance

## Tips

-   Use `bytes` on critical requests to skip the encoding
-   Use dedicated accessors for setting/getting headers, or use the `protocol.http` constants
    for header keys.
