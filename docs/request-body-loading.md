Extra only lazily loads a request's body, which means you can choose to ignore
it, or you can read it in chunks, or read it as a whole, accessing it as bytes
or as fully decoded objects (dicts and `extra.protocol.http.File` objects).

If you want to access the _raw data in chunks_ do something like this:

```
while chunk := await request.read():
	# Do something with 'chunk'
```

Now if you want to acces the _raw data all at once_, do:

```
await request.load()
data = request.body.bytes
```

However, if you want to see if the body has some values or files, you should
do:

```
await request.load()
for value in request.body.values:
	# Do something with value
```

There are some shorthands available in the `request` object to help you
with accessing some common object:

```
await request.load()
request.files # Will return a list of the file objects
request.data  # Will return any form data or JSON data in the request, as a dict
request.raw   # Wlil return the raw bytes of the data
```

Note, however, that you cannot call `request.load()` if you've called
`request.read()` before. The reason is that `request.read()` will consume
the input bytes and not store it anywhere, as opposed to `request.load()` that
will store it in a spool file.

Also, if you know that your request is big and want to break down the loading
in chunks, you can pass a number of bytes to read like `request.load(size=1_000_000)`,
which will return an iterator that you can yield on:

```
while request.load(size=1_000_000):
	yield request.progress
```
