import mongoengine as me
import datetime


class ItemRegisteration(me.Document):
    meta = {"collection": "item_registerations"}

    item = me.ReferenceField("Item", dbref=True)
    description = me.StringField()

    supplier = me.ReferenceField("Supplier", dbref=True)
    user = me.ReferenceField("User", dbref=True)
    quantity = me.IntField(required=True, default=0)
    balance = me.IntField(required=True, default=0)
    price = me.FloatField(required=True)
    status = me.ReferenceField("Status", dbref=True)
    date = me.StringField(required=True)
    expiration_date = me.DateTimeField(required=True, default=datetime.datetime.now())
    location = me.StringField(required=True)


class ItemCheckout(me.EmbeddedDocument):
    item = me.ReferenceField("Item", dbref=True)
    quantity = me.FloatField(required=True)
    price = me.FloatField(required=True)


class Checkout(me.Document):
    meta = {"collection": "checkouts"}

    checkouted_items = me.EmbeddedDocumentListField(ItemCheckout)
    description = me.StringField()
    user = me.ReferenceField("User", dbref=True)
    status = me.ReferenceField("Status", dbref=True)
    checkouted_date = me.DateTimeField(required=True, default=datetime.datetime.now())
