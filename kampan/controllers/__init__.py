from .server import ControllerServer
from ..web import redis_rq
from kampan.utils import config


def create_server():

    settings = config.get_settings()
    server = ControllerServer(settings)
    redis_rq.init_rq(server)

    return server
