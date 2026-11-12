"""ประวัติการแจ้งเตือน MA (#28, #30)

- log ที่ระบบสร้าง (expiry / payment / activation / custom): controller สร้างเป็น ``queued`` ก่อน enqueue
  งานส่งเมลเขียนสถานะสุดท้าย ``sent`` / ``failed`` (failed นับว่าส่งแล้ว ไม่ retry เอง)
- log ที่เพิ่มเอง (manual): ไม่มี ``dedupe_key`` จึงเพิ่มซ้ำวันเดียวกันได้
- กันส่งซ้ำด้วย ``dedupe_key`` (unique + sparse) ไม่ใช้ partialFilterExpression เพราะไม่รู้เวอร์ชัน Mongo ของ production
"""

import datetime

import mongoengine as me

REMINDER_LOG_KINDS = [
    ("expiry", "ใกล้หมดอายุ"),
    ("payment", "จ่ายงวด"),
    ("activation", "activate"),
    ("custom", "วันที่เจาะจง"),
    ("manual", "บันทึกเอง"),
]
REMINDER_LOG_STATUSES = [
    ("queued", "รอส่ง"),
    ("sent", "ส่งแล้ว"),
    ("failed", "ส่งไม่สำเร็จ"),
    ("manual", "บันทึกเอง"),
]
# สถานะที่นับว่าระบบส่ง reminder นั้นไปแล้ว
SYSTEM_LOG_STATUSES = ["queued", "sent", "failed"]


class ReminderLog(me.Document):
    meta = {
        "collection": "reminder_logs",
        "indexes": [
            ("organization", "procurement", "-created_date"),
            ("item", "kind", "trigger_date"),
        ],
    }

    organization = me.ReferenceField("Organization", dbref=True, required=True)
    procurement = me.ReferenceField("Procurement", dbref=True, required=True)
    item = me.ReferenceField("ProcurementItem", dbref=True, required=True)

    kind = me.StringField(choices=REMINDER_LOG_KINDS, required=True)
    # วันที่ reminder ถึงกำหนด (เที่ยงคืน) ของ log ที่เพิ่มเองคือวันที่ติดต่อ
    trigger_date = me.DateTimeField(required=True)
    # ช่วงเตือนที่ทำให้เกิด reminder นี้ เช่น 3m, 15d, 45 (วันที่กรอกเอง), due (วันครบกำหนด)
    offset = me.StringField(max_length=16)
    # เฉพาะ kind=payment
    installment_id = me.ObjectIdField()
    installment_index = me.IntField()

    recipients = me.ListField(me.StringField())
    status = me.StringField(choices=REMINDER_LOG_STATUSES, required=True)
    error = me.StringField()
    note = me.StringField()

    # log ที่ระบบสร้างเท่านั้น (log ที่เพิ่มเองไม่ตั้ง จึงไม่ชน unique)
    dedupe_key = me.StringField(unique=True, sparse=True)

    created_by = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    sent_date = me.DateTimeField()

    def get_kind_label(self) -> str:
        return dict(REMINDER_LOG_KINDS).get(self.kind, self.kind or "-")

    def get_status_label(self) -> str:
        return dict(REMINDER_LOG_STATUSES).get(self.status, self.status or "-")
