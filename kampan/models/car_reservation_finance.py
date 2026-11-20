import datetime

import mongoengine as me

FINANCE_DOCUMENT_TYPES = [
    ("travel", "ใบเบิกค่าใช้จ่ายในการเดินทาง + ใบสำคัญรับเงิน"),
    ("allowance", "ใบเบิกค่าเบี้ยเลี้ยงเดินทาง"),
]


def money():
    return me.DecimalField(min_value=0, precision=2)


class CarReservationFinanceDocument(me.Document):
    """ตัวเลขที่การเงินกรอกในเอกสารเบิกของ พขร. หนึ่งฉบับต่อคำขอต่อประเภทเอกสาร

    เก็บไว้ให้เปิดแก้และดาวน์โหลด PDF ซ้ำได้ (PDF สร้างใหม่จากค่าเหล่านี้ทุกครั้ง ไม่ได้เก็บไฟล์)
    ชื่อฟิลด์ตรงกับ forms.car_reservation_finance.FinanceForm เพื่อ populate_obj/obj= ได้ตรง ๆ
    """

    meta = {
        "collection": "car_reservation_finance_documents",
        "indexes": [
            {"fields": ["reservation", "doc"], "unique": True},
            ("organization", "-updated_date"),
        ],
    }

    organization = me.ReferenceField("Organization", dbref=True, required=True)
    reservation = me.ReferenceField("CarReservation", dbref=True, required=True)
    doc = me.StringField(required=True, choices=FINANCE_DOCUMENT_TYPES)

    memo_number = me.StringField(default="", max_length=64)
    memo_date = me.DateField()
    allowance_type = me.StringField(default="", max_length=32)
    allowance_days = money()
    allowance_amount = money()
    lodging_days = money()
    lodging_amount = money()
    vehicle_cost = money()
    meal_rate_1 = money()
    meal_days_1 = money()
    meal_rate_2 = money()
    meal_days_2 = money()
    evidence_count = me.IntField(min_value=0)

    created_by = me.ReferenceField("User", dbref=True)
    updated_by = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(required=True, default=datetime.datetime.now)
