from flask_mongoengine import MongoEngine
from .users import User
from . import oauth2
from .oauth2 import OAuth2Token
from .items import Item, ItemPosition
from .suppliers import Supplier
from .inventories import CheckinItem, CheckoutItem, RegistrationItem, OrderItem
from .warehouses import Warehouse


db = MongoEngine()


def init_db(app):
    db.init_app(app)
