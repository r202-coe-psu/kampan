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
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    created_by = me.ReferenceField("User", dbref=True)
    last_ip_address = me.StringField()
    user_agent = me.StringField()
    timestamp = me.DateTimeField(required=True, default=datetime.datetime.now)


class CompletedProgressDetail(me.EmbeddedDocument):
    seller_name = me.StringField(required=True, max_length=200)
    money_type = me.StringField(required=True, max_length=50)
    contract_number = me.StringField(required=True, max_length=200)
    purchase_method = me.StringField(required=True, max_length=20)
    start_warranty_date = me.DateField(required=True)
    end_warranty_date = me.DateField(required=True)
    warranty_period = me.IntField(required=True, max_length=20)
    product_number = me.StringField(required=True, max_length=200)
    asset_code = me.StringField(required=True, max_length=200)
    usage_location = me.StringField(required=True, max_length=200)
    account_code = me.StringField(required=True, max_length=200)


class RequisitionTimeline(me.Document):
    meta = {"collection": "requisition_timeline"}
    requisition = me.ReferenceField("Requisition", dbref=True, required=True)
    purchaser = me.ReferenceField("OrganizationUserRole", dbref=True)
    progress = me.EmbeddedDocumentListField(Progress)
    note = me.StringField()
    quotation_winner = me.StringField()
    total_amount = me.FloatField()
    completed_progress_detail = me.EmbeddedDocumentField(CompletedProgressDetail)
    status = me.StringField(default="active", max_length=20)
    updated_date = me.DateTimeField(default=datetime.datetime.now)
    last_updated_by = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    created_by = me.ReferenceField("User", dbref=True)


class RequisitionTimelineLogs(me.Document):
    meta = {"collection": "requisition_timeline_logs"}
    requisition_timeline = me.ReferenceField(
        "RequisitionTimeline", dbref=True, required=True
    )
    progress_status = me.StringField(required=True, max_length=20)
    metadata = me.DictField()
    hashed_metadata = me.StringField()  # from latest progress status and metadata
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    created_by = me.ReferenceField("User", dbref=True)
    last_ip_address = me.StringField()
    user_agent = me.StringField()
