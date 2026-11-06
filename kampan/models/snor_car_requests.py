import datetime

import mongoengine as me

SNOR_REQUEST_TYPES = [
    ("domestic", "ใบขอใช้รถยนต์ไปปฏิบัติงานภายในประเทศ"),
    ("airport", "ใบขอใช้รถ รับ-ส่ง สนามบินหาดใหญ่"),
    ("welfare", "ใบขอใช้รถประเภทสวัสดิการบุคลากร"),
    ("abroad", "ขอใช้รถยนต์พร้อมพนักงานขับรถไปปฏิบัติงานต่างประเทศ"),
]

PROVINCE_SCOPES = [
    ("in_province", "ภายในจังหวัด"),
    ("out_of_province", "ต่างจังหวัด"),
]

SNOR_REQUEST_STATUS = [
    ("pending", "รออนุมัติ"),
    ("active", "อนุมัติแล้ว"),
    ("completed", "เสร็จสิ้น"),
    ("denied", "ไม่อนุมัติ"),
    ("cancel_requested", "ขอยกเลิก"),
    ("cancelled", "ยกเลิก"),
]

STEP_DECISIONS = [("approved", "อนุมัติ"), ("denied", "ไม่อนุมัติ")]

AUDIT_ACTIONS = [
    ("submitted", "ยื่นคำขอ"),
    ("approved", "อนุมัติ"),
    ("denied", "ไม่อนุมัติ"),
    ("cancel_requested", "ขอยกเลิก"),
    ("cancel_confirmed", "รับทราบการยกเลิก"),
    ("cancelled", "ยกเลิก"),
]


class StepApproval(me.EmbeddedDocument):
    step_key = me.StringField(required=True)
    label = me.StringField()
    decision = me.StringField(choices=STEP_DECISIONS)
    decided_by = me.ReferenceField("User", dbref=True)
    decided_at = me.DateTimeField()
    comment = me.StringField(default="")


class SnorAuditLog(me.EmbeddedDocument):
    """ประวัติของคำขอ: ใคร ทำอะไร ขั้นไหน เมื่อไร"""

    action = me.StringField(choices=AUDIT_ACTIONS, required=True)
    actor = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    step_key = me.StringField(default="")
    step_label = me.StringField(default="")
    comment = me.StringField(default="")

    def get_action_display(self):
        return dict(AUDIT_ACTIONS).get(self.action, self.action)


class SnorCarRequest(me.Document):
    meta = {"collection": "snor_car_requests"}

    organization = me.ReferenceField("Organization", dbref=True, required=True)
    division = me.ReferenceField("Division", dbref=True)

    creator = me.ReferenceField("User", dbref=True)
    updater = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )

    requester_unit = me.StringField(default="", max_length=256)  # คณะ/หน่วยงานของผู้ขอ
    phone = me.StringField(default="", max_length=32)
    location = me.StringField(default="", max_length=516, required=True)
    request_reason = me.StringField(default="", max_length=516, required=True)
    departure_datetime = me.DateTimeField(required=True, default=datetime.datetime.now)
    return_datetime = me.DateTimeField(default=datetime.datetime.now)
    passenger_number = me.IntField(min_value=0, required=True, default=0)

    request_type = me.StringField(choices=SNOR_REQUEST_TYPES, required=True)
    province_scope = me.StringField(choices=PROVINCE_SCOPES)

    is_urgent = me.BooleanField(default=False)  # ยื่นล่วงหน้าน้อยกว่าที่กำหนดและผู้ขอยืนยันแล้ว

    status = me.StringField(default="pending", choices=SNOR_REQUEST_STATUS)
    route_snapshot = me.ListField(me.StringField())  # เส้นทางอนุมัติที่ตรึงไว้ตอนยื่น
    current_step = me.IntField(default=0)
    step_approvals = me.ListField(me.EmbeddedDocumentField(StepApproval))
    audit_logs = me.ListField(me.EmbeddedDocumentField(SnorAuditLog))

    car = me.ReferenceField("Car", dbref=True)
    driver = me.ReferenceField("User", dbref=True)
    last_mileage = me.IntField(min_value=0)
    last_mileage_before = me.IntField(min_value=0)
