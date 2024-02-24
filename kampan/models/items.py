from flask import url_for
from email.policy import default
import mongoengine as me
import datetime
from ..models.inventories import Inventory, CheckoutItem


ITEM_FORMAT = [
    ("one to many", "หนึ่งต่อหลายๆ"),
    ("one to one", "หนึ่งต่อหนึ่ง"),
]


class ItemSize(me.EmbeddedDocument):
    width = me.FloatField()
    height = me.FloatField()
    deep = me.FloatField()


class Item(me.Document):
    meta = {"collection": "items"}

    status = me.StringField(default="active")

    name = me.StringField(required=True, max_length=255)
    description = me.StringField()
    organization = me.ReferenceField("Organization", dbref=True)

    one_to_many = me.BooleanField(default=True)
    set_ = me.IntField(required=True, min_value=1, default=1)
    set_unit = me.StringField(required=True, default="ชุด", max_length=50)
    piece_per_set = me.IntField(min_value=1, default=1)
    piece_unit = me.StringField(default="ชิ้น", max_length=50)

    categories = me.StringField(required=True, max_length=255)
    image = me.ImageField(thumbnail_size=(800, 600, False))
    minimum = me.IntField(required=True, min_value=1, default=1)
    barcode_id = me.StringField(required=True, max_length=255)
    notification_status = me.BooleanField(default=True)

    last_updated_by = me.ReferenceField("User", dbref=True)
    created_by = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(required=True, default=datetime.datetime.now)

    def get_items_quantity(self):
        inventories = Inventory.objects(item=self, status="active")
        if inventories:
            sumary = sum([inventory.remain for inventory in inventories])

            if self.one_to_many:
                return f"{sumary // self.piece_per_set} {self.set_unit} {sumary % self.piece_per_set} {self.piece_unit}"
            else:
                return f"{sumary // self.piece_per_set} {self.set_unit}"
        return f"0 {self.set_unit}"

    def get_last_price(self):
        inventories = Inventory.objects(item=self, status="active")
        if inventories:
            return (inventories.order_by("registeration_date")).first().price

    def get_booking_item(self):
        checkout_items = CheckoutItem.objects(
            item=self, status="active", approval_status="pending"
        )
        if checkout_items:
            return sum([checkout_item.quantity for checkout_item in checkout_items])
        return 0


class ItemPosition(me.Document):
    meta = {"collection": "item_positions"}
    status = me.StringField(default="active")

    description = me.StringField(required=True, max_length=255)
    rack = me.StringField(required=True, max_length=255)
    row = me.StringField(max_length=255)
    locker = me.StringField(max_length=255)

    warehouse = me.ReferenceField("Warehouse", dbref=True)

    last_updated_by = me.ReferenceField("User", dbref=True)
    created_by = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(required=True, default=datetime.datetime.now)
