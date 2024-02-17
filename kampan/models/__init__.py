from flask_mongoengine import MongoEngine

from .users import User
from .oauth2 import OAuth2Token
from .items import Item, ItemPosition
from .suppliers import Supplier
from .inventories import (
    Inventory,
    CheckoutItem,
    RegistrationItem,
    OrderItem,
    LostBreakItem,
)
from .warehouses import Warehouse
from .organizations import Organization, Logo, OrganizationUserRole
from .email_templates import EmailTemplate
from .divisions import Division, Endorser, EndorserEmail

db = MongoEngine()


def init_db(app):
    db.init_app(app)


def init_mongoengine(settings):
    import mongoengine as me

    dbname = settings.get("MONGODB_DB")
    host = settings.get("MONGODB_HOST", "localhost")
    port = int(settings.get("MONGODB_PORT", "27017"))
    username = settings.get("MONGODB_USERNAME", "")
    password = settings.get("MONGODB_PASSWORD", "")

    me.connect(db=dbname, host=host, port=port, username=username, password=password)
