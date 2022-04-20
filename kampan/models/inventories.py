import mongoengine as me
import datetime


class ItemRegistation(me.Document):
    meta = {"collection": "item_registrations"}

    description = me.StringField()
    supplier = me.ReferenceField("Supplier", dbref=True)
    user = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)


class CheckinItem(me.Document):
    meta = {"collection": "checkin_items"}

    checkin = me.ReferenceField("Checkin", dbref=True)
    warehouse = me.ReferenceField("Warehouse", dbref=True)
    item = me.ReferenceField("Item", dbref=True)

    quantity = me.IntField(required=True, default=0)
    price = me.FloatField(required=True, default=0)

    registeration_date = me.DateTimeField(
        required=True, default=datetime.datetime.now()
    )
    expiration_date = me.DateTimeField(required=True, default=datetime.datetime.now())
    position = me.ReferenceField("ItemPosition", dbref=True)


class CheckoutItem(me.Document):
    meta = {"collection": "checkout_items"}

    checkout = me.ReferenceField("Checkout", dbref=True)
    checkout_from = me.ReferenceField("Checkin", dbref=True)
    warehouse = me.ReferenceField("Warehouse", dbref=True)
    item = me.ReferenceField("Item", dbref=True)

    quantity = me.FloatField(required=True)
    price = me.FloatField()

    checkout_date = me.DateTimeField(required=True, default=datetime.datetime.now())


class CheckoutItem(me.Document):
    meta = {"collection": "checkout_items"}

    description = me.StringField()
    user = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
