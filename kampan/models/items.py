from flask import url_for
from email.policy import default
import mongoengine as me
import datetime
from ..models.inventories import Inventory


class ItemSize(me.EmbeddedDocument):
    width = me.FloatField()
    height = me.FloatField()
    deep = me.FloatField()


class Item(me.Document):
    meta = {"collection": "items"}
    status = me.StringField(default="active")

    name = me.StringField(required=True, max_length=255)
    description = me.StringField()
    weight = me.FloatField()
    size = me.EmbeddedDocumentField(ItemSize)
    categories = me.ListField(me.StringField(required=True))
    image = me.ImageField(thumbnail_size=(800, 600, False))
    unit = me.StringField(required=True, default="ชุด", max_length=50)
    minimum = me.IntField(required=True, min_value=1, default=1)
    barcode_id = me.StringField(required=True, max_length=255)
    notification_status = me.BooleanField(default=True)

    user = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(required=True, default=datetime.datetime.now)

    def get_items_quantity(self):
        inventories = Inventory.objects(item=self, status="active")
        if inventories:
            return sum([inventory.remain for inventory in inventories])
        return 0

    def get_last_price(self):
        inventories = Inventory.objects(item=self, status="active")
        if inventories:
            return (inventories.order_by("registeration_date")).first().price


class ItemPosition(me.Document):
    meta = {"collection": "item_positions"}
    status = me.StringField(default="active")

    description = me.StringField(required=True, max_length=255)
    rack = me.StringField(required=True, max_length=255)
    row = me.StringField(max_length=255)
    locker = me.StringField(max_length=255)

    warehouse = me.ReferenceField("Warehouse", dbref=True)

    user = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(required=True, default=datetime.datetime.now)
