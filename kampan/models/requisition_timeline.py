import datetime
import mongoengine as me
from bson.objectid import ObjectId

PROGRESS_STATUS_CHOICES = [
    ("request_created", "จัดทำเอกสารขอซื้อ/ขอจ้าง"),
    ("vendor_contacted", "ประสานงานกับร้านค้า/บริษัท"),
    ("details_specified", "ระบุรายละเอียด"),
    ("order_confirmed", "รายงานผลพิจารณา"),
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
    inspection_date = me.DateTimeField()


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
    purchase_method = me.StringField(max_length=50)
    payment_amount = me.FloatField()
    total_amount = me.FloatField()
    fund_usage_amounts = me.DictField(default=dict)
    fund_allocations = me.DictField(default=dict)
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


class RequisitionTimelineItem(me.Document):
    meta = {"collection": "requisition_timeline_items"}
    # reference field
    running_number = me.IntField(required=True)
    requisition_timeline = me.ReferenceField(
        "RequisitionTimeline", dbref=True, required=True
    )
    requisition = me.ReferenceField("Requisition", dbref=True, required=True)
    requisition_item_id = me.ObjectIdField(required=True)
    requisition_item = me.StringField(required=True, max_length=200)

    # section ข้างบนตาราง
    insurance_start_date = me.StringField(required=True, max_length=20)
    seller = me.StringField(required=True, max_length=200)
    insurance_end_date = me.StringField(required=True, max_length=20)
    # section ข้อมูลในตาราง
    responder_user = me.ReferenceField("User", dbref=True)
    serial_number = me.StringField(required=True, max_length=20)
    requisition_item_code = me.StringField(required=True, max_length=20)
    location = me.StringField(required=True, max_length=200)

    status = me.StringField(default="active", max_length=20)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    created_by = me.ReferenceField("User", dbref=True)
