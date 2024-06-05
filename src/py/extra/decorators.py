from typing import ClassVar, Union, Callable, NamedTuple, TypeVar, Iterable, Any

T = TypeVar("T")


class Transform(NamedTuple):
    """Represents a transformation to be applied to a request handler"""

    transform: Callable
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

    @staticmethod
    def Meta(scope: Any) -> dict:
        """Returns the dictionary of meta attributes for the given value."""
        if isinstance(scope, type):
            if not hasattr(scope, "__extra__"):
                setattr(scope, "__extra__", {})
            return getattr(scope, "__extra__")
        else:
            return scope.__dict__


def on(
    priority=0, **methods: Union[str, list[str], tuple[str, ...]]
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


def expose(
    priority=0, compress=False, contentType=None, raw=False, **methods
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
        meta.setdefault(Extra.EXPOSE, True)
        meta.setdefault(Extra.EXPOSE_JSON, None)
        meta.setdefault(Extra.EXPOSE_RAW, raw)
        meta.setdefault(Extra.EXPOSE_COMPRESS, compress)
        meta.setdefault(Extra.EXPOSE_CONTENT_TYPE, contentType)
        # This is copy and paste of the @on body
        v = meta.setdefault(Extra.ON, [])
        meta.setdefault(Extra.ON_PRIORITY, int(priority))
        for http_method, url in list(methods.items()):
            if type(url) not in (list, tuple):
                url = (url,)
            for method in http_method.upper().split("_"):
                for _ in url:
                    if method == "JSON":
                        function.__dict__[Extra.EXPOSE_JSON] = _
                    else:
                        v.append((method, _))
        return function

    return decorator


def when(*predicates):
    """The @when(...) decorate allows to specify that the wrapped method will
    only be executed when the given predicate (decorated with `@on`)
    succeeds."""

    def decorator(function):
        v = Extra.Meta(function).setdefault(Extra.WHEN, [])
        v.extend(predicates)
        return function

    return decorator


def pre(transform: Callable) -> Callable[[T], T]:
    """Registers the given `transform` as a pre-processing step of the
    decorated function."""

    def decorator(function: T, *args, **kwargs) -> T:
        v = Extra.Meta(function).setdefault(Extra.PRE, [])
        v.append(Transform(transform, args, kwargs))
        return function

    return decorator


def post(transform) -> Callable[[T], T]:
    """Registers the given `transform` as a post-processing step of the
    decorated function."""

    def decorator(function: T, *args, **kwargs) -> T:
        v = Extra.Meta(function).setdefault(Extra.POST, [])
        v.append(Transform(transform, args, kwargs))
        return function

    return decorator


# EOF
