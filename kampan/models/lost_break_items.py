from email.policy import default
import mongoengine as me
import datetime
from kampan import models


class LostBreakItem(me.Document):
    # ไอเทมที่ชำรุด หรือ เสียหาย
    mete = {"collection": "lost_break_items"}
    status = me.StringField(default="active")

    user = me.ReferenceField("User", dbref=True)
    item = me.ReferenceField("Item", dbref=True)

    lost_from = me.ReferenceField("Inventory", dbref=True)
    warehouse = me.ReferenceField("Warehouse", dbref=True)
    description = me.StringField(max_length=255)
    quantity = me.IntField(required=True, min_value=1, default=1)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
