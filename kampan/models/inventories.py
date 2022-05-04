import mongoengine as me
import datetime


class RegistrationItem(me.Document):
    meta = {"collection": "registration_items"}
    receipt_id = me.StringField(required=True, max_length=255)
    description = me.StringField()
    supplier = me.ReferenceField("Supplier", dbref=True)
    user = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)


class CheckinItem(me.Document):
    meta = {"collection": "checkin_items"}

    registration = me.ReferenceField("RegistrationItem", dbref=True)
    warehouse = me.ReferenceField("Warehouse", dbref=True)
    item = me.ReferenceField("Item", dbref=True)

    quantity = me.IntField(required=True, default=0)
    remain = me.IntField(required=True, default=0)
    price = me.FloatField(required=True, default=0)

    registeration_date = me.DateTimeField(
        required=True, default=datetime.datetime.now()
    )
    expiration_date = me.DateTimeField(required=True, default=datetime.datetime.now())
    position = me.ReferenceField("ItemPosition", dbref=True)

class OrderItem(me.Document):
    meta = {"collection": "order_items"}

    ordernumber = me.IntField()
    description = me.StringField()
    user = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)

class CheckoutItem(me.Document):
    meta = {"collection": "checkout_items"}

    order = me.ReferenceField("OrderItem", dbref=True)
    checkout_from = me.ReferenceField("CheckinItem", dbref=True)
    warehouse = me.ReferenceField("Warehouse", dbref=True)
    item = me.ReferenceField("Item", dbref=True)

    quantity = me.FloatField(required=True)
    price = me.FloatField()
    message = me.StringField()

    checkout_date = me.DateTimeField(required=True, default=datetime.datetime.now())



