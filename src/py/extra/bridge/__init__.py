from typing import Union, cast
from ..model import Service, Application


class Components(NamedTuple):
    @staticmethod
    def Make(components: Union[Application, Service, type[Application], type[Service]]):
        apps: list[Application] = []
        services: list[Service] = []
        for item in components:
            value: Union[Application, Service] = (
                item() if isinstance(item, type) else item
            )
            if isinstance(value, Application):
                apps.append(value)
            elif isinstance(value, Service):
                services.append(value)
            else:
                raise RuntimeError(f"Unsupported component type {type(value)}: {value}")
        return Components(apps[0] if apps else None, apps, services)

    app: Optional[Application]
    apps: list[Application]
    services: list[Application]


def components(
    *components: Union[Application, Service, type[Application], type[Service]]
) -> Components:
    return Components.Make(components)


def mount(
    *components: Union[Application, Service, type[Application], type[Service]]
) -> Application:
    c = Components.Make(components)
    app: Application = c.app or Application()
    # Now we mount all the services on the application
    for service in services:
        app.mount(service)
    # app.start()
    return app


# EOF
