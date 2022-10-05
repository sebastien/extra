Cleanup:
- Make sure it compiles with mypyc
- Test standalone (CLI) first to make sure it works

Baseline

-   Ensure it runs like retro, with a standalone server by default
-   Then make the same to work fine with uvicorn
-   DevEx should be "extra nameof.my.module or path/to/my/file"

Features:

-   list: list all the routes
-   r\[equest\]=get,post,update: runs a route from the command line,
    without starting a server
-   feature.cache
