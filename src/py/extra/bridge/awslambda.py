from ..model import Application, Service
from ..bridge import mount, components
from ..logging import error
from ..protocol.http import HTTPRequest, HTTPParser
from typing import Callable, Any, Union

# TODO: Use aws-lambda-rie to test that
TLambdaHandler = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]

# TODO: os.environ[AWS_REGION]
# TODO: Convert Response to JSON format
#       see https://docs.aws.amazon.com/lambda/latest/dg/python-handler.html

# SEE: Event - https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-concepts.html#gettingstarted-concepts-event
# SEE: Context - https://docs.aws.amazon.com/lambda/latest/dg/python-context.html


class AWSLambdaHandler:
    def __init__(self, application: Application):
        self.app = application

    def __call__(
        self, event: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        return {}


def run(*services: Union[Application, Service]) -> AWSLambdaHandler:
    """Runs the given services/application using the embedded AsyncIO HTTP server."""
    return AWSLambdaHandler(mount(*services))


# EOF
