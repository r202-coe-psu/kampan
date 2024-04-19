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
    set_ = me.IntField(required=True, min_value=1, default=1)
    quantity = me.IntField(required=True, min_value=1, default=1)
    checkout_date = me.DateTimeField(required=True, default=datetime.datetime.now())


class CheckoutItem(me.Document, BaseCheckoutItem):
    # รายการนำเข้าอุปกรณ์ออก
    meta = {"collection": "checkout_items"}
    approval_status = me.StringField(default="pending")

    def get_amount_items(self):
        sumary = (self.set_ * self.item.piece_per_set) + self.quantity
        return sumary
