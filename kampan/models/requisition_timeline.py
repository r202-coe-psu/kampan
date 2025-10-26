import datetime
import mongoengine as me
from bson.objectid import ObjectId

PROGRESS_STATUS_CHOICES = [
    ("request_created", "จัดทำเอกสารขอซื้อ/ขอจ้าง"),
    ("vendor_contacted", "ประสานงานกับร้านค้า/บริษัท"),
    ("order_confirmed", "ยืนยันการสั่งซื้อ/สั่งจ้าง"),
    ("awaiting_delivery", "รอส่งมอบพัสดุ"),
    ("inspection", "ตรวจรับพัสดุ"),
    ("payment_processed", "เบิกจ่าย"),
    ("completed", "เสร็จสิ้น"),
]


class Progress(me.EmbeddedDocument):
    progress_status = me.StringField(
        required=True,
        max_length=20,
        choices=PROGRESS_STATUS_CHOICES,
    )
    issued_by = me.ReferenceField("User")
    issued_date = me.ReferenceField("User", dbref=True)
    last_ip_address = me.StringField()
    user_agent = me.StringField()
    timestamp = me.DateTimeField(required=True, default=datetime.datetime.now)


class RequisitionProgress(me.Document):
    meta = {"collection": "requisition_timeline"}
    requisition = me.ReferenceField("Requisition", dbref=True, required=True)
    purchaser = me.ReferenceField("OrganizationUserRole", dbref=True)
    progress = me.EmbeddedDocumentListField(Progress)
    updated_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_by = me.ReferenceField("User", dbref=True)
