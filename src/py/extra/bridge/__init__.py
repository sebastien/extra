from typing import Union, cast
import types
from ..model import Service, Application


def mount(*services: Union[Application, Service]) -> Application:
    # This extracts and instanciates the services and applications that
    # are given here.
    services = [_() if isinstance(_, type) or isinstance(
        _, types.FunctionType) else _ for _ in services]
    not_ok = [_ for _ in services if not isinstance(
        _, Application) and not isinstance(_, Service)]
    if not_ok:
        raise Exception(
            f"Given services not all Service or Application instances: {not_ok}")
    app = [_ for _ in services if isinstance(_, Application)]
    services = [_ for _ in services if isinstance(_, Service)]
    app = cast(Application, app[0] if app else Application())
    # Now we mount all the services on the application
    for service in services:
        app.mount(service)
    # NOTE: We don't call app.start just yet
    return app
