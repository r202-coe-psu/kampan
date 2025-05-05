from email.policy import default
import mongoengine as me
import datetime
from kampan import models

LOST_BREAK_STATUS = [
    ("active", "อนุมัติสำเร็จ"),
    ("disactive", "ยกเลิก"),
    ("denied", "ปฏิเสธ"),
    ("pending", "รอการตรวจสอบ"),
]


class LostBreakItem(me.Document):
    # ไอเทมที่ชำรุด หรือ เสียหาย
    mete = {"collection": "lost_break_items"}
    status = me.StringField(default="pending", choices=LOST_BREAK_STATUS)
    organization = me.ReferenceField("Organization", dbref=True)
    user = me.ReferenceField("User", dbref=True)
    item = me.ReferenceField("Item", dbref=True)

    lost_from = me.ReferenceField("Inventory", dbref=True)
    warehouse = me.ReferenceField("Warehouse", dbref=True)
    description = me.StringField(max_length=255)
    quantity = me.IntField(required=True, default=1)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)

    def get_all_price(self):
        return self.item.get_last_price_per_piece() * self.quantity

    def get_color_status(self):
        if self.status == "active":
            return " text-success "
        elif self.status == "denied":
            return " text-error "
        elif self.status == "pending":
            return " text-orange-500 "
