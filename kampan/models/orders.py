import mongoengine as me
import datetime


class ItemRegisteration(me.Document):
    meta = {"collection": "item_registerations"}

    item = me.ReferenceField("Item", dbref=True)
    description = me.StringField()

    supplier = me.ReferenceField("Supplier", dbref=True)
    user = me.ReferenceField("User", dbref=True)
    quantity = me.IntField(required=True, default=0)
    price = me.FloatField(required=True, default=0)
    status = me.ReferenceField("Status", dbref=True)
    registeration_date = me.DateTimeField(required=True, default=datetime.datetime.now())
    expiration_date = me.DateTimeField(required=True, default=datetime.datetime.now())
    location = me.ReferenceField("Location", dbref=True)


class ItemCheckout(me.Document):
    meta = {"collection": "item_checkouts"}

    checkout = me.ReferenceField("Checkout", dbref=True)
    item = me.ReferenceField("Item", dbref=True)
    quantity = me.FloatField(required=True)
    price = me.FloatField(required=True)


class Checkout(me.Document):
    meta = {"collection": "checkouts"}

    description = me.StringField()
    user = me.ReferenceField("User", dbref=True)
    # status = me.ReferenceField("Status", dbref=True)
    checkouted_date = me.DateTimeField(required=True, default=datetime.datetime.now())
