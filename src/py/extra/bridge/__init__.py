from typing import Union, cast
from ..model import Service, Application


def mount(*services: Union[Application, Service]) -> Application:
    # This extracts and instanciates the services and applications that
    # are given here.
    services = [_() if isinstance(_, type) else _ for _ in services]
    app = [_ for _ in services if isinstance(_, Application)]
    services = [_ for _ in services if isinstance(_, Service)]
    app = cast(Application, app[0] if app else Application())
    # Now we mount all the services on the application
    for service in services:
        app.mount(service)
    app.start()
    return app
