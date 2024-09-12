from typing import (
    LiteralString,
    Optional,
    Iterable,
    Iterator,
    Union,
    Callable,
    cast,
)
from mypy_extensions import KwArg, VarArg

# TODO: Define a Chunk to define a way to pre-rendere chunks of a Node, so that
# we get fast serialization when writing to. The key thing, just like with JSON
# is to cache as much as we can and write it out.

# --
# HTMPL defines functions to create HTML templates

HTML_EMPTY: list[LiteralString] = (
    "area base br col embed hr img input link meta param source track wbr".split()
)
HTML_ESCAPED = str.maketrans(
    {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#x27;"}
)

HTML_QUOTED = str.maketrans({"&": "&amp;", '"': "&quot;"})


def escape(text: str) -> str:
    return text.translate(HTML_ESCAPED)


def quoted(text: Optional[str]) -> str:
    return text.translate(HTML_QUOTED) if text else ""


TNodeContent = Union["Node", str, bool, float, int]
TAttributeContent = str | bool | float | int | None


class Node:
    __slots__ = ["name", "ns", "attributes", "children"]

    def __init__(
        self,
        name: str,
        ns: Optional[str] = None,
        children: Optional[Iterable[TNodeContent]] = None,
        attributes: Optional[dict[str, TAttributeContent]] = None,
    ):
        self.name = name
        self.ns = ns
        self.attributes: dict[str, TAttributeContent] = attributes or {}
        self.children: list[TNodeContent] = [_ for _ in children] if children else []

    def iterHTML(self) -> Iterator[str]:
        yield from self.iterXML(html=True)

    def iterXML(self, html=False) -> Iterator[str]:
        if self.name == "#raw":
            yield str(self.attributes.get("#value") or "")
        elif self.name == "#text":
            yield escape(str(self.attributes.get("#value") or ""))
        elif self.name == "--":
            yield "<!--"
            for _ in self.children:
                if isinstance(_, Node):
                    yield from _.iterXML()
                elif _ is None:
                    pass
                else:
                    yield str(_)
            yield "-->"
        elif self.name == "!CDATA":
            yield "<![DATA["
            for _ in self.children:
                if isinstance(_, Node):
                    yield from _.iterXML(html=html)
                elif _ is None:
                    pass
                else:
                    yield str(_)

            yield "]]>"
        elif self.name == "!DOCTYPE":
            yield "<!DOCTYPE "
            for _ in self.children:
                if isinstance(_, Node):
                    yield from _.iterXML(html=html)
                elif _ is None:
                    pass
                else:
                    yield str(_)
            yield ">\n"
        else:
            yield f"<{self.name}"
            for k, v in (self.attributes or {}).items():
                yield f' {k}="{quoted(str(v))}"' if v is not None else f" {k}"
            if not self.children:
                if html:
                    yield ">" if self.name in HTML_EMPTY else f"></{self.name}>"
                else:
                    yield " />"
            else:
                yield ">"
                for _ in self.children:
                    if isinstance(_, Node):
                        yield from _.iterXML(html=html)
                    elif _ is None:
                        pass
                    else:
                        yield str(_)
                yield f"</{self.name}>"

    def __call__(self, *content: Union[str, "Node"]):
        for _ in content:
            self.children.append(text(_) if isinstance(_, str) else _)
        return self

    def __str__(self) -> str:
        return "".join(self.iterHTML())


def text(text) -> Node:
    return Node("#text", attributes={"#value": text})


def node(
    name: str,
    ns: Optional[str] = None,
    children: Optional[Iterable[TNodeContent]] = None,
    attributes: Optional[dict[str, TAttributeContent]] = None,
    **attrs: Optional[str],
) -> Node:
    a: dict[str, TAttributeContent] = {}
    for d in (attributes, attrs):
        if d:
            a.update(d)
    return Node(
        name,
        ns,
        children=[text(_) if isinstance(_, str) else _ for _ in children or ()],
        attributes=a,
    )


NodeFactory = Callable[
    [
        VarArg(Iterable[Node | str]),
        KwArg(str | None),
    ],
    Node,
]


def nodeFactory(name: str, ns: Optional[str] = None) -> NodeFactory:
    def f(*children: TNodeContent, **attributes: TAttributeContent):
        content: list[TNodeContent] = []
        for _ in children:
            if isinstance(_, list):
                content += _
            elif isinstance(_, tuple):
                content += list(_)
            else:
                content.append(_)
        attrs: dict[str, TAttributeContent] = {}
        for k, v in attributes.items():
            if k == "children":
                content += cast(
                    list[TNodeContent],
                    (
                        v
                        if isinstance(v, list)
                        else (
                            [_ for _ in cast(tuple, v)] if isinstance(v, tuple) else [v]
                        )
                    ),
                )
            elif k == "_":
                attrs["class"] = v
            else:
                attrs[k] = v
        return node(name, ns, content, attrs)

    f.__name__ = name
    return cast(NodeFactory, f)


HTML_TAGS: list[LiteralString] = (
    """\
a abbr address area article aside audio b base bdi bdo blockquote body br
button canvas caption cite code col colgroup data datalist dd del details dfn
dialog div dl dt em embed fieldset figcaption figure footer form h1 h2 h3 h4 h5
h6 head header hr html i iframe img input ins kbd label legend li link main map
mark meta meter nav noscript object ol optgroup option output p param picture
pre progress q rp rt ruby s section samp script section select small source span strong
style sub summary sup table tbody td template textarea tfoot th thead time
title tr track u ul var video wbr\
""".split()
)


class Markup:
    __slots__ = ["_factories", "_name"]

    def __init__(self, name: str, factories: dict[str, NodeFactory]):
        self._name: str = name
        self._factories: dict[str, NodeFactory] = factories

    def __getattribute__(self, name: str):
        if name.startswith("_"):
            return super().__getattribute__(name)
        else:
            factories = self._factories
            if name not in factories:
                raise KeyError(
                    f"No tag {name}, pick one of {','.join(factories.keys())}"
                )
            else:
                return factories[name]


def markup(name: str, tags: list[str | LiteralString]) -> Markup:
    return Markup(name, {_: nodeFactory(_) for _ in tags})


H: Markup = markup("html", HTML_TAGS)


def raw(html: str) -> Node:
    return Node("#raw", attributes={"#value": html})


def html(
    *nodes: Node, doctype: str | None = None, children: Node | list[Node] | None = None
) -> Iterator[str]:
    if doctype:
        yield f"{doctype}\n" if doctype.startswith("<!") else f"<!DOCTYPE {doctype}>\n"
    for _ in nodes:
        yield from _.iterHTML()
    if children is None:
        pass
    elif isinstance(children, Node):
        yield from children.iterHTML()
    else:
        for _ in children:
            yield from _.iterHTML()


if __name__ == "__main__":
    import sys

    for _ in html(H.html(H.body(H.h1("Hello, world!")))):
        sys.stdout.write(_)
# EOF
