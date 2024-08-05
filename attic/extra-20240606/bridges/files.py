#!/usr/bin/env python
# NOTE: Disabling for mypyc
# import time
# import fuse
# from .model import Application, Service
# from errno import ENOENT
# from stat import S_IFDIR, S_IFREG
# from typing import Optional, Union, Iterable
#
# # SEE: https://github.com/fusepy/fusepy
#
#
# class FUSEBridge(fuse.Operations):
#     def getattr(self, path, fh=None):
#         uid, gid, pid = fuse.fuse_get_context()
#         if path == "/":
#             st = dict(st_mode=(S_IFDIR | 0o755), st_nlink=2)
#         elif path == "/uid":
#             size = len("%s\n" % uid)
#             st = dict(st_mode=(S_IFREG | 0o444), st_size=size)
#         elif path == "/gid":
#             size = len("%s\n" % gid)
#             st = dict(st_mode=(S_IFREG | 0o444), st_size=size)
#         elif path == "/pid":
#             size = len("%s\n" % pid)
#             st = dict(st_mode=(S_IFREG | 0o444), st_size=size)
#         else:
#             raise fuse.FuseOSError(ENOENT)
#         st["st_ctime"] = st["st_mtime"] = st["st_atime"] = time.time()
#         return st
#
#     def read(self, path, size, offset, fh):
#         uid, gid, pid = fuse.fuse_get_context()
#
#         def encoded(x):
#             return ("%s\n" % x).encode("utf-8")
#
#         if path == "/uid":
#             return encoded(uid)
#         elif path == "/gid":
#             return encoded(gid)
#         elif path == "/pid":
#             return encoded(pid)
#
#         raise RuntimeError("unexpected path: %r" % path)
#
#     def readdir(self, path):
#         return [".", "..", "uid", "gid", "pid"]
#
#     # Disable unused operations:
#     access = None
#     flush = None
#     getxattr = None
#     listxattr = None
#     open = None
#     opendir = None
#     release = None
#     releasedir = None
#     statfs = None
#
#
# def run(server, path: str, foreground=True, allowOther=True):
#     # handler = fuse.FUSE(server, "pouet", foreground=True, allow_other=True)
#     pass
