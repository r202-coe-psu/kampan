# Inventories --> คลังสินค้า, สินค้าคงเหลือ

from email.policy import default
import mongoengine as me
import datetime
from kampan import models


class Inventory(me.Document):
    # อุปกรณ์
    meta = {"collection": "inventories"}
    status = me.StringField(default="active", required=True)

    registration = me.ReferenceField("RegistrationItem", dbref=True)
    warehouse = me.ReferenceField("Warehouse", dbref=True)
    organization = me.ReferenceField("Organization", dbref=True)

    item = me.ReferenceField("Item", dbref=True)
    # bill = me.FileField()

    set_ = me.IntField(required=True, min_value=1, default=1)
    quantity = me.IntField(required=True, min_value=1, default=1)
    remain = me.IntField(required=True, default=0)
    price = me.DecimalField(required=True, default=0)

    registeration_date = me.DateTimeField(
        required=True, default=datetime.datetime.now()
    )
    expiration_date = me.DateTimeField()
    position = me.ReferenceField("ItemPosition", dbref=True)

    # notification_status = me.BooleanField(default=True)
    created_by = me.ReferenceField("User", dbref=True)

    def get_checkout_items(self):
        return models.CheckoutItem.objects(checkout_from=self, status="active")

    def get_bill_file_name(self):
        if self.registration.bill:
            return self.registration.bill.filename
        else:
            return "ไม่พบบิล"

    def get_all_price(self):
        return self.price * self.quantity

    def get_price_per_piece(self):
        return round(self.price / self.item.piece_per_set, 2)


class InventoryEngagementFile(me.Document):
    meta = {"collection": "inventory_engagement_file"}

    file = me.FileField()
    status = "waiting"
    created_by = me.ReferenceField("User", dbref=True)
    organization = me.ReferenceField("Organization", dbref=True)
    registration = me.ReferenceField("RegistrationItem", dbref=True)

    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )
