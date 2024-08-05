from ..http.model import HTTPRequest, HTTPResponse
from ..decorators import post

# SEE: http://stackoverflow.com/questions/16386148/why-browser-do-not-follow-redirects-using-xmlhttprequest-and-cors/20854800#20854800


@post
def cors(
    request: HTTPRequest, response: HTTPResponse, allowAll: bool = True
) -> HTTPResponse:
    """A post decorator that ensures that the cords headers are set."""
    return setCORSHeaders(
        response, origin=request.getHeader("Origin"), allowAll=allowAll
    )


def setCORSHeaders(
    request: HTTPRequest | HTTPResponse, *, origin=None, allowAll=True
) -> HTTPResponse:
    """Takes the given request or response, and return (a response) with the CORS headers set properly.

    See <https://en.wikipedia.org/wiki/Cross-origin_resource_sharing>
    """
    if isinstance(request, HTTPRequest):
        response: HTTPResponse = request.respond(status=200)
        origin = origin or request.getHeader("Origin")
    else:
        response = request
    # SEE: https://remysharp.com/2011/04/21/getting-cors-working
    # If the request returns a 0 status code, it's likely because of CORS
    response.setHeaders(
        {
            "Access-Control-Allow-Origin": origin if origin and not allowAll else "*",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS, HEAD, INFO, PUT, DELETE, UPDATE",
        }
    )
    return response


# EOF
