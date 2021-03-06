from flask_mongoengine import MongoEngine

from .users import User
from .oauth2 import OAuth2Token
from .items import Item, ItemPosition
from .suppliers import Supplier
from .inventories import Inventory, CheckoutItem, RegistrationItem, OrderItem, LostBreakItem
from .warehouses import Warehouse


db = MongoEngine()


def init_db(app):
    db.init_app(app)
