from ..protocols.http import HTTPRequest, HTTPResponse
from ..decorators import post

# SEE: http://stackoverflow.com/questions/16386148/why-browser-do-not-follow-redirects-using-xmlhttprequest-and-cors/20854800#20854800


@post
def cors(request: HTTPRequest, response: HTTPResponse, allowAll: bool = True):
    return setCORSHeaders(
        response, origin=request.getHeader(b"Origin"), allowAll=allowAll
    )


def setCORSHeaders(
    request: HTTPRequest | HTTPResponse, *, origin=None, allowAll=True
) -> HTTPResponse:
    """Takes the given request or response, and return (a response) with the CORS headers set properly.

    See <https://en.wikipedia.org/wiki/Cross-origin_resource_sharing>
    """
    if isinstance(request, HTTPRequest):
        origin = origin or request.getHeader(b"Origin")
        response = HTTPResponse.Create().init(status=200)
    else:
        response = request
    # SEE: https://remysharp.com/2011/04/21/getting-cors-working
    # If the request returns a 0 status code, it's likely because of CORS
    response.setHeader(
        b"Access-Control-Allow-Origin", origin if origin and not allowAll else b"*"
    )
    response.setHeader(b"Access-Control-Allow-Headers", b"*")
    response.setHeader(
        b"Access-Control-Allow-Methods",
        b"GET, POST, OPTIONS, HEAD, INFO, PUT, DELETE, UPDATE",
    )
    return response


# EOF
