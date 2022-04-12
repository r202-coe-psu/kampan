from flask_mongoengine import MongoEngine
from .users import User
from . import oauth2
from .oauth2 import OAuth2Token
from .items import ItemSize, Item, ItemPosition
from .inventories import CheckinItem, CheckoutItem, Checkout
from .warehouses import Warehouse


db = MongoEngine()


def init_db(app):
    db.init_app(app)
