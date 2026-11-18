from email.policy import default
import mongoengine as me
import datetime
import decimal
from decimal import Decimal
from kampan import models
from kampan.models.item_checkouts import BaseCheckoutItem


class ApprovedCheckoutItem(me.Document, BaseCheckoutItem):
    meta = {"collection": "approved_checkout_items"}

    warehouse = me.ReferenceField("Warehouse", dbref=True)
    # checkout_from = me.ReferenceField("Inventory", dbref=True)
    approved_date = me.DateTimeField()
    price = me.DecimalField(
        default=Decimal("0"),
        min_value=0,
        max_value=1e12,
        precision=2,
        rounding=decimal.ROUND_HALF_EVEN,
    )
    aprroved_amount = me.IntField(default=0)
