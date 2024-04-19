from email.policy import default
import mongoengine as me
import datetime
from kampan import models
from kampan.models.item_checkouts import BaseCheckoutItem


class ApprovedCheckoutItem(me.Document, BaseCheckoutItem):
    meta = {"collection": "approved_checkout_items"}

    warehouse = me.ReferenceField("Warehouse", dbref=True)
    # checkout_from = me.ReferenceField("Inventory", dbref=True)
    approved_date = me.DateTimeField()
    price = me.DecimalField(default=0.0)
    aprroved_amount = me.IntField(default=0)
