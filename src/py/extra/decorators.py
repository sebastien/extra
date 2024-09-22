from typing import ClassVar, Union, Callable, NamedTuple, TypeVar, Any, cast

from .http.model import HTTPRequest, HTTPResponse

T = TypeVar("T")


class Transform(NamedTuple):
    """Represents a transformation to be applied to a request handler"""

    transform: Callable[..., Any]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]


class Extra:
    """Defines Extra attributes used by decorators"""

    ON: ClassVar[str] = "_extra_on"
    ON_PRIORITY: ClassVar[str] = "_extra_on_priority"
    EXPOSE: ClassVar[str] = "_extra_expose"
    EXPOSE_JSON: ClassVar[str] = "_extra_expose_json"
    EXPOSE_RAW: ClassVar[str] = "_extra_expose_raw"
    EXPOSE_COMPRESS: ClassVar[str] = "_extra_expose_compress"
    EXPOSE_CONTENT_TYPE: ClassVar[str] = "_extra_expose_content_type"
    POST: ClassVar[str] = "_extra_post"
    PRE: ClassVar[str] = "_extra_pre"
    WHEN: ClassVar[str] = "_extra_when"
    # When using MyPy, we can't dynamically patch values, so instead we're
    # collecting annotations by object id.
    Annotations: ClassVar[dict[int, dict[str, Any]]] = {}

    @staticmethod
    def Meta(scope: Any, *, strict: bool = False) -> dict[str, Any]:
        """Returns the dictionary of meta attributes for the given value."""
        if isinstance(scope, type):
            if not hasattr(scope, "__extra__"):
                setattr(scope, "__extra__", {})
            return cast(dict[str, Any], getattr(scope, "__extra__"))
        else:
            if hasattr(scope, "__dict__"):
                return cast(dict[str, Any], scope.__dict__)
            elif strict:
                raise RuntimeError(f"Metadata cannot be attached to object: {scope}")
            else:
                sid = id(scope)
                if sid not in Extra.Annotations:
                    Extra.Annotations[sid] = {}
                return Extra.Annotations[sid]


def on(
    priority: int = 0, **methods: Union[str, list[str], tuple[str, ...]]
) -> Callable[[T], T]:
    """The @on decorator is one of the main important things you will use within
    Retro. This decorator allows to wrap an existing method and indicate that
    it will be used to process an HTTP request.

    The @on decorator can take `GET` and `POST` arguments, which take either a
    string or a list of strings, each describing an URI pattern (see
    @Dispatcher) that when matched, will trigger the method.

    The decorated method must take a `request` argument, as well as the same
    arguments as those used in the pattern.

    For instance:

    >    @on(GET='/list/{what:string}'

    implies that the wrapped method is like

    >    def listThings( self, request, what ):
    >        ....

    it is also crucial to return a a response at the end of the call:

    >        returns request.respond(...)

    The @Request class offers many methods to create and send responses."""

    def decorator(function: T) -> T:
        # TODO: Should be using annotations
        meta = Extra.Meta(function)
        v = meta.setdefault(Extra.ON, [])
        meta.setdefault(Extra.ON_PRIORITY, priority)
        for http_methods, url in list(methods.items()):
            urls = (url,) if type(url) not in (list, tuple) else url
            for http_method in http_methods.upper().split("_"):
                for _ in urls:
                    v.append((http_method, _))
        return function

    return decorator


# TODO: We could have an extractor method that would extract specific parameters from
# the request body. Ex:
# @expose(POST="/api/ads", name=lambda _:_.get("name"), ....)


class Expose(NamedTuple):
    json: Any | None = None
    raw: bool = False
    compress: bool = False
    contentType: str | None = None


def expose(
    priority: int = 0,
    compress: bool = False,
    contentType: str | None = None,
    raw: bool = False,
    **methods: str,
) -> Callable[[T], T]:
    """The @expose decorator is a variation of the @on decorator. The @expose
    decorator allows you to _expose_ an existing Python function as a JavaScript
    (or JSON) producing method.

    Basically, the @expose decorator allows you to automatically bind a method to
    an URL and to ensure that the result will be JSON-ified before being sent.
    This is perfect if you have an existing python class and want to expose it
    to the web."""

    def decorator(function: T) -> T:
        meta = Extra.Meta(function)

        # This is copy and paste of the @on body
        v = meta.setdefault(Extra.ON, [])
        meta.setdefault(Extra.ON_PRIORITY, int(priority))
        json_data: Any | None = None
        for http_method, url in list(methods.items()):
            urls: list[str] | tuple[str, ...] = (url,) if isinstance(url, str) else url
            for method in http_method.upper().split("_"):
                for _ in urls:
                    if method == "JSON":
                        json_data = _
                    else:
                        v.append((method, _))
        meta.setdefault(
            Extra.EXPOSE,
            Expose(
                json=json_data,
                raw=raw,
                compress=compress,
                contentType=contentType,
            ),
        )
        return function

    return decorator


def when(*predicates: Callable[..., bool]) -> Callable[..., T]:
    """The @when(...) decorate allows to specify that the wrapped method will
    only be executed when the given predicate (decorated with `@on`)
    succeeds."""

    def decorator(function: T, *args: Any, **kwargs: Any) -> T:
        v = Extra.Meta(function).setdefault(Extra.WHEN, [])
        v.extend(predicates)
        return function

    return decorator


def pre(transform: Callable[..., bool]) -> Callable[..., T]:
    """Registers the given `transform` as a pre-processing step of the
    decorated function."""

    def decorator(function: T, *args: Any, **kwargs: Any) -> T:
        v = Extra.Meta(function).setdefault(Extra.PRE, [])
        v.append(Transform(transform, args, kwargs))
        return function

    return decorator


def post(
    transform: Callable[[HTTPRequest, HTTPResponse], HTTPResponse]
) -> Callable[[T], T]:
    """Registers the given `transform` as a post-processing step of the
    decorated function."""

    def decorator(function: T, *args: Any, **kwargs: Any) -> T:
        v = Extra.Meta(function).setdefault(Extra.POST, [])
        v.append(Transform(transform, args, kwargs))
        return function

    return decorator


# EOF
