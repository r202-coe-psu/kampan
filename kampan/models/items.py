from flask import url_for
from email.policy import default
import mongoengine as me
from mongoengine import Q
import datetime
from kampan import models


ITEM_FORMAT = [
    ("one to many", "หนึ่งต่อหลายๆ"),
    ("one to one", "หนึ่งต่อหนึ่ง"),
]

ITEM_SNAPSHOT = [
    ("carry", "ยกยอด"),
    ("check", "เช็คสต๊อก"),
]


class ItemSize(me.EmbeddedDocument):
    width = me.FloatField()
    height = me.FloatField()
    deep = me.FloatField()


class Item(me.Document):
    meta = {
        "collection": "items",
        "indexes": ["name", "created_date"],
    }

    status = me.StringField(default="pending")

    name = me.StringField(required=True, max_length=255)
    description = me.StringField()
    remark = me.StringField()
    organization = me.ReferenceField("Organization", dbref=True)

    item_format = me.StringField(
        required=True, choices=ITEM_FORMAT, default=ITEM_FORMAT[0][0]
    )
    set_ = me.IntField(required=True, min_value=1, default=1)
    set_unit = me.StringField(required=True, default="ชุด", max_length=50)
    piece_per_set = me.IntField(min_value=1, default=1)
    piece_unit = me.StringField(default="ชิ้น", max_length=50)

    categories = me.ReferenceField("Category", dbref=True)
    image = me.ImageField()
    minimum = me.IntField(required=True, min_value=0, default=0)
    barcode_id = me.StringField(max_length=255)
    notification_status = me.BooleanField(default=True)

    last_updated_by = me.ReferenceField("User", dbref=True)
    created_by = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )

    def get_items_quantity(self):
        inventories = models.Inventory.objects(item=self, status="active")
        if inventories:
            sumary = sum([inventory.remain for inventory in inventories])

            if self.item_format == "one to many":
                return f"{sumary // self.piece_per_set} {self.set_unit} " + (
                    (str(sumary % self.piece_per_set) + " " + str(self.piece_unit))
                    if (sumary % self.piece_per_set) != 0
                    else ""
                )
            else:
                return f"{sumary // self.piece_per_set} {self.set_unit}"
        return f"0 {self.set_unit}"

    def get_amount_items(self):
        inventories = models.Inventory.objects(item=self, status="active")
        if inventories:
            sumary = sum([inventory.remain for inventory in inventories])
            return sumary // self.piece_per_set
        return 0

    def get_amount_pieces(self):
        inventories = models.Inventory.objects(item=self, status="active")
        if inventories:
            sumary = sum([inventory.remain for inventory in inventories])
            return sumary
        return 0

    def get_last_price(self):
        inventories = models.Inventory.objects(item=self, status="active")
        if inventories:
            return inventories.order_by("created_date").first().price

    def get_last_price_per_piece(self):
        value = self.get_last_price()
        if value:

            return round(value / self.piece_per_set, 2)

        return ""

    def get_remaining_balance(self):
        value = self.get_last_price()
        amount_item = self.get_amount_items()
        amount_piece = self.get_amount_pieces()
        if value:
            set_remaining = (value * amount_item) + (
                (amount_piece % self.piece_per_set)
                * round(value / self.piece_per_set, 2)
            )
            return set_remaining
        return ""

    def get_booking_item(self):
        checkout_items = models.CheckoutItem.objects(
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
    organization = me.ReferenceField("Organization", dbref=True)
    warehouse = me.ReferenceField("Warehouse", dbref=True)

    last_updated_by = me.ReferenceField("User", dbref=True)
    created_by = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(required=True, default=datetime.datetime.now)


class ItemSnapshot(me.Document):
    meta = {"collection": "item_snapshots"}
    type_ = me.StringField(default="carry", choices=ITEM_SNAPSHOT, required=True)

    item = me.ReferenceField("Item", dbref=True)
    amount = me.IntField()
    amount_pieces = me.IntField()
    last_price = me.DecimalField()
    last_price_per_piece = me.DecimalField()

    remaining_balance = me.DecimalField()
    status = me.StringField(default="active")

    organization = me.ReferenceField("Organization", dbref=True)

    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(required=True, default=datetime.datetime.now)

    def get_amount_pieces(self):
        return self.amount_pieces % self.item.piece_per_set
