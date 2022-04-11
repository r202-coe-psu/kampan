import mongoengine as me
import datetime


class Inventory(me.Document):
    meta = {"collection": "inventories"}

    item = me.ReferenceField("Item", dbref=True)
    description = me.StringField()

    supplier = me.ReferenceField("Supplier", dbref=True)

    user = me.ReferenceField("User", dbref=True)

    quantity = me.IntField(required=True, default=0)
    price = me.FloatField(required=True, default=0)

    registeration_date = me.DateTimeField(
        required=True, default=datetime.datetime.now()
    )
    expiration_date = me.DateTimeField(required=True, default=datetime.datetime.now())
    position = me.ReferenceField("ItemPosition", dbref=True)


class ItemCheckout(me.Document):
    meta = {"collection": "item_checkouts"}

    checkout = me.ReferenceField("Checkout", dbref=True)
    inventory = me.ReferenceField("Inventory", dbref=True)

    quantity = me.FloatField(required=True)
    price = me.FloatField()


class Checkout(me.Document):
    meta = {"collection": "checkouts"}

    description = me.StringField()
    user = me.ReferenceField("User", dbref=True)
    checkouted_date = me.DateTimeField(required=True, default=datetime.datetime.now)
