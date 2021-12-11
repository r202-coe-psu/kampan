from flask_mongoengine import MongoEngine
from .users import User
from . import oauth2
from .oauth2 import OAuth2Token
from .items import ItemSize, Item 
from .orders import ItemRegisteration ,Checkout 
from .stocks import Supplier ,Inventory ,ItemStatus 
__all__ = ["User"]

db = MongoEngine()


def init_db(app):
    db.init_app(app)
