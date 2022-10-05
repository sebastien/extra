from typing import Optional, Callable, Any
from ..util.tree import NamedNode


class Topics:
    """A topic tree backed by the `NamedNode` tree. The topic tree is used
    to bind handlers that provide an effect upon subscription."""

    INSTANCE: "Topics" = None

    @classmethod
    def Instance(cls):
        if not cls.INSTANCE:
            cls.INSTANCE = cls()
        return cls.INSTANCE

    @classmethod
    def Get(cls, path: str):
        return cls.Instance().get(path)

    @classmethod
    def Ensure(cls, path: str) -> NamedNode:
        return cls.Instance().ensure(path)

    def __init__(self):
        self.root = NamedNode()

    def get(self, path: str, strict=False) -> Optional[NamedNode]:
        return self.root.resolve(path, strict=strict)

    def ensure(self, path: str) -> NamedNode:
        return self.root.ensure(path)


def pub(path: str, **fields: Any) -> bool:
    """Publishes the given message at the given path."""
    topic = Topics.Get(path)
    if topic:
        topic.trigger("pub", fields)
        return True
    else:
        return False


def sub(path: str, callback: Callable) -> NamedNode:
    """Subscribes to the given path, triggering the given callback when
    the path is activated."""
    return Topics.Ensure(path).on("pub", callback)


def unsub(path: str, callback) -> NamedNode:
    """The inverse of 'sub'"""
    return Topics.Ensure(path).off("pub", callback)


# EOF
