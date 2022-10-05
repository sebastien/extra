from typing import Optional, Iterable, Callable, Union, Any, cast
from pathlib import Path
from io import BytesIO
import os
import re
import time
import weakref
import json
import re
import gzip

__doc__ = """
Defines different types of nodes that can be used to work with tree-like
structures. Each tree structure supports a few useful features:

- event dispatching
- depth-first walking
- update and children update timestamps (activated with `touch`).
"""

# -----------------------------------------------------------------------------
#
# EVENT
#
# -----------------------------------------------------------------------------


class Event:
    """Wraps some data and binds it to a name. An event is propagated up
    a tree until its `isPropagating` attribute is set to `False`."""

    def __init__(self, name: str, data: Optional[Any] = None):
        self.name = name
        self.data = data
        self.created = time.time()
        self.target: Optional["Node"] = None
        self.isPropagating: bool = True

    def stop(self):
        self.isPropagating = False
        return self

    def __str__(self):
        return f"<Event {self.name}={self.data}>"


# -----------------------------------------------------------------------------
#
# NODE
#
# -----------------------------------------------------------------------------


class Node:
    """A basic implementation of a tree."""

    ID = 0
    SEPARATOR = "."

    def __init__(self):
        self.id: int = Node.ID
        Node.ID += 1
        self._children: list["Node"] = []
        self.parent: Optional["Node"] = None
        self.data: Optional[Any] = None
        self.meta: dict[str, Any] = {}
        self.handlers: Optional[dict[str, list[Callable]]] = None
        self.changed = time.time()
        self.childChanged = self.changed

    @property
    def name(self):
        return self.id

    @property
    def cacheKey(self):
        """The key is used for caching."""
        return self.path

    @property
    def path(self):
        if self.parent:
            if self.parent.isRoot:
                return self.name
            else:
                return f"{self.parent.path}{self.SEPARATOR}{self.name}"
        else:
            return "#root"

    @property
    def depth(self) -> int:
        node = self
        depth = 0
        while node.parent:
            node = node.parent
            depth += 1
        return depth

    @property
    def root(self) -> "Node":
        node = self
        while node.parent:
            node = node.parent
        return node

    @property
    def ancestors(self) -> Iterable["Node"]:
        node = self.parent
        while node:
            yield node
            node = node.parent

    @property
    def descendants(self) -> Iterable["Node"]:
        for child in self.children:
            yield child
            yield from child.descendants

    @property
    def leaves(self) -> Iterable["Node"]:
        if not self.children:
            yield self
        else:
            for child in self.children:
                yield from child.leaves

    @property
    def isRoot(self) -> bool:
        return not self.parent

    @property
    def isLeaf(self) -> bool:
        return not self.children

    # NOTE: We use an accesor as filesystem nodes do not store children
    # in memory.
    @property
    def children(self):
        return self._children

    def setMeta(self, meta):
        self.meta = meta
        return self

    def setData(self, data):
        self.data = data
        return self

    def on(self, event: str, callback: Callable):
        """Binds an event handler (`callback`) to the given even path. A
        handler can only be bound once."""
        self.handlers = self.handlers or {}
        handlers = self.handlers.setdefault(event, [])
        assert (
            callback not in handlers
        ), f"Registering callback twice in node {self}: {callback}"
        handlers.append(callback)
        return self

    def off(self, event: str, callback: Callable):
        """Unbinds an event handler (`callback`) from the given even path,
        which requires the event handler to have previously been bound."""
        handlers: Optional[list[Callable]] = (
            self.handlers.get(event) if self.handlers else None
        )
        if handlers:
            assert (
                callback not in handlers
            ), f"Callback not registered in node {self}: {callback}"
            handlers.remove(callback)
        return self

    def trigger(self, event: str, data=None) -> Event:
        """Creates a new event with the given name and data, dispatching it
        up."""
        event = Event(event, data)
        return self._dispatchEvent(event)

    def _dispatchEvent(self, event: Event):
        """Dispatches the event in this node, triggering any registered callback
        and propagating the even to the parent."""
        handlers = self.handlers.get(event.name, ()) if self.handlers else ()
        event.target = self
        for h in handlers:
            if h(event) is False:
                event.stop()
                break
        if event.isPropagating and self.parent:
            self.parent._dispatchEvent(event)
        return event

    def add(self, node: "Node") -> "Node":
        if node not in self.children:
            node.parent = self
            self.children.append(node)
        return node

    def touch(self):
        """Marks this node as changed, capturing the timestamp and
        propagating the change up."""
        changed = time.time()
        self.changed = changed
        for _ in self.ancestors:
            _.childChanged = max(changed, _.childChanged)
        return self

    def walk(self) -> Iterable["Node"]:
        yield self
        for c in self.children:
            yield from c.walk()

    def toPrimitive(self):
        return {
            "id": self.id,
            "meta": self.meta,
            "children": [_.toPrimitive() for _ in self.children],
        }

    def __str__(self):
        return f"<Node:{self.id} +{len(self.children)}>"


# -----------------------------------------------------------------------------
#
# NAMED NODE
#
# -----------------------------------------------------------------------------


class NamedNode(Node):
    """Named nodes make trees where children are named instead
    of being anonymous and indexed. This structure makes it easy to
    implement registries and filesystem-like hierarchies."""

    def __init__(
        self, name: Optional[str] = None, parent: Optional["NamedNode"] = None
    ):
        super().__init__()
        self._name: Optional[str] = name
        self._children: dict[str, "NamedNode"] = dict()
        self.parent: Optional["NamedNode"] = None
        # We bind the node if a parent was set
        if parent:
            assert name, "Cannot set a parent without setting a name."
            parent.set(name, self)

    @property
    def name(self):
        return self._name

    @property
    def children(self):
        return list(self._children.values())

    @children.setter
    def children(self, children):
        self.clear()
        for child in children:
            assert child.name, "When setting a name, children must already be named"
            self.set(child.name, child)

    def rename(self, name: str):
        if self.parent:
            self.parent.set(name, self)
        else:
            self._name = name
        return self

    def removeAt(self, name: str):
        raise NotImplementedError

    def clear(self):
        return [child.detach() for child in self.children]

    def remove(self, node: "NamedNode"):
        assert node.parent == self
        assert self._children[node.name] == node
        del self._children[node.name]
        node.parent = None
        return node

    def detach(self):
        return self.parent.remove(self) if self.parent else self

    def add(self, node: "Node") -> "NamedNode":
        assert isinstance(
            node, NamedNode
        ), "NamedNode can only take a compatible subclass"
        assert node.name, "Node can only be added if named"
        return self.set(node.name, node)

    def set(self, key: str, node: "NamedNode") -> "NamedNode":
        assert key, f"Cannot set node with key '{key}' in: {self.path}"
        # We remove the previous child, if any
        previous = self._children.get(key)
        if previous:
            previous.detach()
        # We bind the node first
        node._name = key
        node.parent = self
        # And we assign it
        self._children[key] = node
        return node

    def has(self, key: str) -> bool:
        return key in self._children

    def get(self, key: str) -> Optional["NamedNode"]:
        return self._children[key] if key in self._children else None

    def resolve(self, path: str, strict=True) -> Optional["NamedNode"]:
        context: NamedNode = self
        for k in path.split(self.SEPARATOR):
            if not context.has(k):
                return None if strict else context
            else:
                context = cast(NamedNode, context.get(k))
        return context

    def ensure(self, path: str) -> "NamedNode":
        context: NamedNode = self
        for k in path.split(self.SEPARATOR):
            if not context:
                break
            elif not k:
                # TODO: This should be a warning here
                continue
            elif not context.has(k):
                context = context.set(k, self.__class__(name=k))
                assert (
                    not context or context.parent
                ), f"Created node should have parent {context}"
            else:
                context = cast(NamedNode, context.get(k))
                assert (
                    not context or context.parent
                ), f"Retrieved node should have parent {context}"
        return context

    def walk(self) -> Iterable["NamedNode"]:
        yield self
        for c in self.children:
            yield from c.walk()

    def toPrimitive(self):
        res = super().toPrimitive()
        res["name"] = self.name
        return res

    def __getitem__(self, name: str):
        return self.children[name]

    def __str__(self):
        return f"<NamedNode:{self.name}:{self.id} +{len(self.children)}>"


# -----------------------------------------------------------------------------
#
# FILESYSTEM NODE
#
# -----------------------------------------------------------------------------


class FilesystemNode(NamedNode):
    """The filesystem node provides a relatively easy way to manipulate a
    tree persisted on the filesystem. Children nodes are stored in a weak value
    dict."""

    SEPARATOR = "/"

    @staticmethod
    def DATA_PREDICATE(_: str) -> bool:
        return _.endswith(".data.json.gz")

    @staticmethod
    def META_PREDICATE(_: str) -> bool:
        return _.endswith(".meta.json.gz")

    @staticmethod
    def DATA_EXTRACT(_: str) -> bool:
        return _[: -(len(".data.json.gz"))]

    @staticmethod
    def META_EXTRACT(_: str) -> bool:
        return _[: -(len(".meta.json.gz"))]

    DATA_FORMAT: str = "{name}.data.json.gz"
    META_FORMAT: str = "{name}.meta.json.gz"

    @staticmethod
    def SERIALIZE(data: Any, stream: BytesIO):
        return json.dump(data, stream)

    @staticmethod
    def DESERIALIZE(stream: BytesIO):
        return json.load(stream)

    RE_NAME_NORMALIZE = re.compile(r"[\\/ ]")
    CHAR_NAME_NORMALIZE = "_"

    @classmethod
    def NormalizeKey(cls, key: Optional[str]):
        return cls.RE_NAME_NORMALIZE.sub(cls.CHAR_NAME_NORMALIZE, key) if key else key

    def __init__(
        self,
        name: Optional[str] = None,
        parent: Optional["FilesystemNode"] = None,
        base: Union[None, str, Path] = None,
    ):
        super().__init__(self.NormalizeKey(name), parent)
        self._base: Optional[Path] = (
            Path(base)
            if isinstance(base, str)
            else base
            if isinstance(base, Path)
            else None
        )
        self._children: weakref.WeakValueDictionary[
            str, FilesystemNode
        ] = weakref.WeakValueDictionary()

    # FIXME: These should probably be cached, as it's a lot of objects
    # created on property access.

    @property
    def metaPath(self) -> Path:
        if not self.parent:
            # FIXME: This might not work all the time, esp. if the basepath
            # has a trailing /
            return Path(self.META_FORMAT.format(name=self.basePath))
        else:
            assert (
                self.name
            ), f"If the node has a parent, it must have a name: {self.path}"
            name = self.META_FORMAT.format(name=self.name)
            return cast(FilesystemNode, self.parent).basePath.joinpath(name)

    @property
    def dataPath(self) -> Path:
        if not self.parent:
            # FIXME: This might not work all the time, esp. if the basepath
            # has a trailing /
            return Path(self.DATA_FORMAT.format(name=self.basePath))
        else:
            assert (
                self.name
            ), f"If the node has a parent, it must have a name: {self.path}"
            name = self.DATA_FORMAT.format(name=self.name)
            return cast(FilesystemNode, self.parent).basePath.joinpath(name)

    @property
    def basePath(self) -> Path:
        """The base path is the path where this nodes files would be."""
        # NOTE: A node without parent has no name, so we use the base
        return (
            self._base if not self.parent else self.parent.basePath.joinpath(self.name)
        )

    @property
    def hasBase(self):
        return bool(self.root._base)

    @property
    def children(self) -> list["FilesystemNode"]:
        return list(self.pullChildren().values())

    def pullChildren(self) -> dict[str, "FilesystemNode"]:
        """Pulls/syncs the children from the filesystem, returning a map. This
        has the effect of updating the `_children` map."""
        if not self.hasBase:
            return {}
        else:
            path = self.basePath
            # NOTE: We're caching the result in the _children weak dict
            if not path or not path.is_dir():
                return {}
            else:
                res = {}
                # We reuse the children weak map, which means we might
                # need to re-create some nodes.
                children = self._children
                for p in path.iterdir():
                    n = None
                    if p.is_dir():
                        n = p.name
                    elif self.__class__.DATA_PREDICATE(p.name):
                        n = self.__class__.DATA_EXTRACT(p.name)
                    elif self.__class__.META_PREDICATE(p.name):
                        n = self.__class__.META_EXTRACT(p.name)
                    if n:
                        v = children.get(n)
                        # NOTE: We use `n` and not `p.name` as we want
                        # the path stripped of any suffix, which is
                        # why `n` is extracted from `p.name`
                        if not v:
                            # The node has vanished or was not there, so
                            # we create it.
                            v = FilesystemNode(n, self)
                            # We need to store in res, because we're using
                            # a weak value for children
                            children[n] = v
                            res[n] = v
                        else:
                            res[n] = v
                return res

    def has(self, key: str) -> bool:
        # We test for children, meta or data files
        return (
            self.dataPath.exists() or self.metaPath.exists() or self.basePath.exists()
        )

    def set(self, key: str, node: "FilesystemNode") -> "FilesystemNode":
        key = self.NormalizeKey(key)
        if node:
            node.key = key
        return super().set(key, node)

    def get(self, key: str) -> Optional["FilesystemNode"]:
        key = self.NormalizeKey(key)
        node = self._children.get(key)
        # NOTE: We're pulling from the weak dictionary
        if node:
            return node
        elif self.has(key):
            node = FilesystemNode(key, self)
            self._children[key] = node
            return node
        else:
            return None

    def clear(self):
        """Clears the data and metadata associated with this node."""
        return self.write(None, None)

    def write(self, data=False, meta=False):
        """A utility method that can be used to directly set the data and/or
        metadata and commit it to the filesystem."""
        if data is not False:
            self.data = data
        if meta is not False:
            self.meta = meta
        if data is not False or meta is not False:
            return self.push(data=data is not False, meta=meta is not False)
        return self

    def push(self, data=True, meta=True):
        """Pushes the data and metadata to the local filesystem"""
        if data:
            data_path = self.dataPath
            if self.data is None:
                if data_path.exists():
                    data_path.unlink()
            else:
                with gzip.open(self._ensurePathParent(data_path), "wt") as f:
                    self.__class__.SERIALIZE(self.data, f)
        if meta:
            meta_path = self.metaPath
            if self.meta is None:
                if meta_path.exists():
                    meta_path.unlink()
            else:
                with gzip.open(self._ensurePathParent(meta_path), "wt") as f:
                    self.__class__.SERIALIZE(self.meta, f)
        if meta or data:
            self.touch()
        return self

    def pull(self, data=True, meta=True, merge=None):
        """Pulls the data and metadata from the local filesystem"""
        # NOTE: We test for `self.{data,meta}` to decide if we merge or not,
        # which might not be the best strategy.
        if data:
            pulled_data = None
            data_path = self.dataPath
            if data_path.exists():
                with gzip.open(self._ensurePathParent(data_path), "rt") as f:
                    pulled_data = self.__class__.DESERIALIZE(f)
            self.data = (
                merge(self.data, pulled_data) if merge and self.data else pulled_data
            )
        if meta:
            pulled_meta = None
            meta_path = self.metaPath
            if meta_path.exists():
                with gzip.open(self._ensurePathParent(meta_path), "rt") as f:
                    pulled_meta = self.__class__.DESERIALIZE(f)
            self.meta = (
                merge(self.meta, pulled_meta) if merge and self.meta else pulled_meta
            )
        return self

    def copyTo(self, store, meta=True, data=True, limit=-1):
        target = store.ensure(self.path)
        self.pull(meta=meta, data=data)
        if meta is True:
            target.meta = self.meta
        if data is True:
            target.data = self.data
        target.push(meta=meta, data=data)
        if limit != 0:
            for child in self.children:
                self.get(child).copyTo(store, meta=meta, data=data, limit=limit - 1)
        return target

    def _ensurePathParent(self, path: Path = None):
        """Makes sure that the parent of the path exists"""
        parent = self.basePath if not path else path.parent
        if not parent.exists():
            os.makedirs(parent)
        return path

    def __contains__(self, name: str):
        return self.has(name)

    def __getitem__(self, name: str):
        if name in self._children:
            return self._children[name]
        elif self.has(name):
            return self.get(name)
        else:
            raise KeyError(f"Node {self.path} has no children with name: {name}")

    def __str__(self):
        return f"<FilesystemNode:{self.name}:{self.id} +{len(self.children)}>"


# -----------------------------------------------------------------------------
#
# FORMATTER
#
# -----------------------------------------------------------------------------


class ASCII:
    @classmethod
    def Format(cls, node: Node, prefix="") -> Iterable[str]:
        # FIXME: It's ~OK but needs improvement
        p = "─┬" if node.children else "──"
        yield f"{prefix}{p} {node.name or ':root'}"
        last_child = len(node.children) - 1
        prefix = " " * len(prefix)
        for i, child in enumerate(node.children):
            yield from cls.Format(child, prefix + (" ├" if i < last_child else " └"))


class Graphviz:
    @classmethod
    def Format(cls, root: Node) -> Iterable[str]:
        yield "digraph {"
        for node in root.walk():
            if isinstance(node, NamedNode):
                yield f"  {node.id}[label={json.dumps(node.path or ':root')}];"
            else:
                yield f"  {node.id};"
            for child in node.children:
                yield f"  {node.id}->{child.id};"
        yield "}"


def toASCIILines(node):
    yield from ASCII.Format(node)


def toASCII(node):
    return "\n".join(toASCIILines(node))


def toGraphvizLines(node):
    yield from Graphviz.Format(node)


def toGraphviz(node):
    return "\n".join(toGraphvizLines(node))


def store(path):
    return FilesystemNode(base=path)


# EOF
