from email.policy import default
import mongoengine as me
import datetime
from kampan import models


class BaseCheckoutItem:
    status = me.StringField(default="active")

    order = me.ReferenceField("OrderItem", dbref=True)

    message = me.StringField()
    item = me.ReferenceField("Item", dbref=True)
    user = me.ReferenceField("User", dbref=True)
    set_ = me.IntField(required=True, min_value=0, default=0)
    piece = me.IntField(required=True, min_value=0, default=0)
    quantity = me.IntField(required=True, min_value=0, default=1)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now())
    organization = me.ReferenceField("Organization", dbref=True)


class CheckoutItem(me.Document, BaseCheckoutItem):
    # รายการนำเข้าวัสดุออก
    meta = {"collection": "checkout_items"}
    approval_status = me.StringField(default="pending")
    approved_date = me.DateTimeField()
    inventories = me.ListField(me.ReferenceField("Inventory", dbref=True))

    def get_amount_items(self):
        sumary = (self.set_ * self.item.piece_per_set) + self.quantity
        return sumary

    def get_all_price(self):
        return self.item.get_last_price_per_piece() * self.get_amount_items()
