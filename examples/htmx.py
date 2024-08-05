from extra.utils.htmpl import Node, H

# TODO: We could define a Format model that turns a JSON API into a corresponding
# Node structure using slots and template operations.


def htmx(*nodes: Node) -> Node:
    return H.html(
        H.head(H.script(src="https://unpkg.com/htmx.org@1.9.12")),
        H.body("Hello, world", *nodes),
    )


print(htmx())
