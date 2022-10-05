import json
import pickle
import os
import shutil
import gzip

__doc__ = """
A set of generic functions to read and write data to the filesystem, supporting
different serialisation and compression formats.
"""

COMPRESSION = {
    ".gz": gzip.open,
}

WRITERS = {
    ".json": ("wt", lambda v, f: json.dump(v, f)),
    ".pickle": ("wb", lambda v, f: picke.dump(v, f)),
}

READERS = {
    ".json": ("rb", lambda f: json.load(f)),
    ".pickle": ("rb", lambda f: pickle.load(f)),
    ".log": ("rb", lambda f: f.readlines()),
    ".txt": ("rb", lambda f: f.read()),
}

# def syncWrite( self,  data, append=False ):
#     """Saves/appends to the file at the given path."""
#     flags  = os.O_WRONLY | os.O_CREAT
#     parent = os.path.dirname(os.path.abspath(path))
#     if not os.path.exists(parent) and mkdir: os.makedirs(parent)
#     # FIXME: The file is created a +x... weird!
#     if hasattr(os, "O_DSYNC"):
#         flags = flags | os.O_DSYNC
#     flags = flags | (os.O_APPEND if append else os.o_TRUNC)
#     fd = os.open(path, flags)
#     try:
#         os.write(fd, data)
#         os.close(fd)
#     except Exception as e:
#         os.close(fd)
#         raise e
#     return self


def ensure(path):
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent)
    return path


def cp(fromPath, toPath):
    ensure(toPath)
    shutil.copy(fromPath, toPath)


def write(value, path):
    opener = getFileOpener(path)
    for key in WRITERS:
        if path.endswith(key):
            mode, writer = WRITERS[key]
            with opener(ensure(path), mode) as f:
                writer(value, f)
            return value
    if isinstance(value, str):
        with opener(ensure(path), "wt") as f:
            f.write(f)
    elif isinstance(bytes, str):
        with opener(ensure(path), "wb") as f:
            f.write(value)
    else:
        raise ValueError(
            f"No writer found for {path} and value {value}, pick one of {','.join(WRITERS.keys())}"
        )


def read(path):
    opener = getFileOpener(path)
    if not os.path.exists(path):
        return FileNotFoundError(f"File not found: {path}")
    for key in READERS:
        if path.endswith(key):
            mode, reader = READERS[key]
            with opener(path, mode) as f:
                return reader(f)
    else:
        with opener(path, "rb") as f:
            return f.read()


def getFileOpener(path):
    """Returns the file opening function that corresponds to the given path."""
    for key in COMPRESSION:
        if path.endswith(key):
            return COMPRESSION[key]
    return open


# EOF
