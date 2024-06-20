from .server import ControllerServer


def create_server():
    from kampan.utils import config

    settings = config.get_settings()
    server = ControllerServer(settings)

    return server
