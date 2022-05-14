from typing import Union, cast
from ..model import Service, Application


def mount(
    *components: Union[Application, Service, type[Application], type[Service]]
) -> Application:
    # This extracts and instanciates the services and applications that
    # are given here.
    expanded_components: list[Union[Application, Service]] = [
        cast(Union[Application, Service], _() if isinstance(_, type) else _)
        for _ in components
    ]
    services: list[Service] = [_ for _ in expanded_components if isinstance(_, Service)]
    app: Application = next(
        (_ for _ in expanded_components if isinstance(_, Application)), Application()
    )
    # Now we mount all the services on the application
    for service in services:
        app.mount(service)
    # app.start()
    return app


# EOF
