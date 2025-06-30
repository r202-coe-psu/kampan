# Inventories --> คลังสินค้า, สินค้าคงเหลือ

from email.policy import default
import mongoengine as me
import datetime
from kampan import models


class Inventory(me.Document):
    # วัสดุ
    meta = {"collection": "inventories"}
    status = me.StringField(default="active", required=True)

    registration = me.ReferenceField("RegistrationItem", dbref=True)
    warehouse = me.ReferenceField("Warehouse", dbref=True)
    position = me.ReferenceField("ItemPosition", dbref=True)
    organization = me.ReferenceField("Organization", dbref=True)

    item = me.ReferenceField("Item", dbref=True)
    # bill = me.FileField()

    set_ = me.IntField(required=True, min_value=0, default=0)
    quantity = me.IntField(required=True, min_value=0, default=0)
    remain = me.IntField(required=True, default=0)
    price = me.DecimalField(required=True, default=0)

    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    expiration_date = me.DateTimeField()

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
        if self.item.item_format == "one to one":
            return self.get_price_per_piece() * self.quantity
        return self.price * self.set_

    def get_all_quantity(self):
        return self.item.piece_per_set * self.quantity

    def get_price_per_piece(self):
        return round(self.price / self.item.piece_per_set, 2)

    def get_created_date(self):
        if self.created_date >= self.registration.created_date:
            return self.created_date.strftime("%d/%m/%Y")
        return self.registration.created_date.strftime("%d/%m/%Y")


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
