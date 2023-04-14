from typing import Optional, Iterable, Iterator, Union, ClassVar, Callable, Type
from mypy_extensions import KwArg, VarArg

# --
# HTMPL defines functions to create HTML templates

HTML_ESCAPED = str.maketrans(
    {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#x27;"}
)

HTML_QUOTED = str.maketrans({"&": "&amp;", '"': "&quot;"})


def escape(text: str) -> str:
    return text.translate(HTML_ESCAPED)


def quoted(text: Optional[str]) -> str:
    return text.translate(HTML_QUOTED) if text else ""


class Node:
    def __init__(
        self,
        name: str,
        ns: Optional[str] = None,
        children: Optional[Iterable["Node"]] = None,
        attributes: Optional[dict[str, Optional[str]]] = None,
    ):
        self.name = name
        self.ns = ns
        self.attributes = attributes or {}
        self.children: list["Node"] = [_ for _ in children] if children else []

    def iterHTML(self) -> Iterator[str]:
        yield from self.iterXML(html=True)

    def iterXML(self, html=False) -> Iterator[str]:
        if self.name == "#text":
            yield escape(self.attributes.get("#value") or "")
        elif self.name == "--":
            yield "<!--"
            for _ in self.children:
                yield from _.iterXML()
            yield "-->"
        elif self.name == "!CDATA":
            yield "<![DATA["
            for _ in self.children:
                yield from _.iterXML(html=html)
            yield "]]>"
        elif self.name == "!DOCTYPE":
            yield "<!DOCTYPE "
            for _ in self.children:
                yield from _.iterXML(html=html)
            yield ">\n"
        else:
            yield f"<{self.name}"
            for k, v in (self.attributes or {}).items():
                yield f' {k}="{quoted(v)}"'
            if not self.children:
                if html:
                    yield f"></{self.name}>"
                else:
                    yield " />"
            else:
                yield ">"
                for _ in self.children:
                    yield from _.iterXML(html=html)
                yield f"</{self.name}>"

    def __call__(self, *content: Union[str, "Node"]):
        for _ in content:
            self.children.append(text(_) if isinstance(_, str) else _)
        return self


def text(text) -> Node:
    return Node("#text", attributes={"#value": text})


def node(
    name: str,
    ns: Optional[str] = None,
    children: Optional[Iterable[Union[Node, str]]] = None,
    attributes: Optional[dict[str, Optional[str]]] = None,
    **attrs: Optional[str],
) -> Node:
    a = {}
    if attributes:
        a.update(attributes)
    if attrs:
        a.update(attrs)
    return Node(
        name,
        ns,
        children=[text(_) if isinstance(_, str) else _ for _ in children or ()],
        attributes=a,
    )


NodeFactory = Callable[
    [
        VarArg(Iterable[Union[Node, str]]),
        KwArg(Optional[str]),
    ],
    Node,
]


def nodeFactory(name: str, ns: Optional[str] = None) -> NodeFactory:
    def f(*children: Union[Node, str], **attributes: Optional[str]):
        return node(name, ns, children, {k: v for k, v in attributes.items()})

    f.__name__ = name
    return f


HTML_TAGS = """\
a abbr address area article aside audio b base bdi bdo blockquote body br
button canvas caption cite code col colgroup data datalist dd del details dfn
dialog div dl dt em embed fieldset figcaption figure footer form h1 h2 h3 h4 h5
h6 head header hr html i iframe img input ins kbd label legend li link main map
mark meta meter nav noscript object ol optgroup option output p param picture
pre progress q rp rt ruby s section samp script section select small source span strong
style sub summary sup table tbody td template textarea tfoot th thead time
title tr track u ul var video wbr\
""".split()


def markup(name: str, tags: list[str]):
    class HFactory(type):
        def __new__(mcls, name: str, bases: tuple, attrs: dict) -> Type:
            annotations = {}
            attrs["__annotations__"] = annotations
            for tag in tags:
                annotations[tag] = ClassVar[Callable]
                attrs[tag] = nodeFactory(tag)
            return super().__new__(mcls, name, bases, attrs)

    class M(metaclass=HFactory):
        pass

    M.__name__ = "html"

    return M


H = markup("html", HTML_TAGS)


def html(*nodes: Node) -> str:
    for _ in nodes:
        yield from _.iterHTML()


if __name__ == "__main__":
    import sys

    for _ in html(H.html(H.body(H.h1("Hello, world!")))):
        sys.stdout.write(_)
# EOF
