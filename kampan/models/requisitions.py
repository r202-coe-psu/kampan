import datetime
import mongoengine as me
from bson.objectid import ObjectId

from kampan.models.procurement import CATEGORY_CHOICES

COMMITTEE_TYPE_CHOICES = [
    ("specification", "คณะกรรมการกำหนดคุณสมบัติ"),
    ("procurement", "คณะกรรมการจัดซื้อ"),
    ("inspection", "คณะกรรมการตรวจรับ"),
]

COMMITTEE_POSITION_CHOICES = [
    ("chairman", "ประธานกรรมการ"),
    ("member", "กรรมการ"),
]

STATUS_CHOICES = [
    ("pending", "Pending"),
    ("progress", "Progress"),
    ("incomplete", "Incomplete"),
    ("complete", "Complete"),
]


class Committees(me.EmbeddedDocument):
    _id = me.ObjectIdField(required=True, default=ObjectId)
    member = me.ReferenceField("OrganizationUserRole", dbref=True)
    committee_type = me.StringField(max_length=50, required=True)
    committee_position = me.StringField(max_length=50, required=True)


class RequisitionItem(me.EmbeddedDocument):
    _id = me.ObjectIdField(required=True, default=ObjectId)
    product_name = me.StringField(max_length=100, required=True)
    quantity = me.IntField(min_value=1, required=True)
    category = me.StringField(max_length=20, choices=CATEGORY_CHOICES, required=True)
    amount = me.DecimalField(required=True, min_value=0, max_value=1e12, precision=2)
    currency = me.StringField(max_length=10)


class ApprovalHistory(me.EmbeddedDocument):
    _id = me.ObjectIdField(required=True, default=ObjectId)
    approver = me.ReferenceField("OrganizationUserRole", dbref=True)
    approver_role = me.StringField(max_length=50)
    action = me.StringField(
        max_length=20,
        choices=[("approved", "Approved"), ("rejected", "Rejected")],
        required=True,
    )
    reason = me.StringField(max_length=25)
    last_ip_address = me.StringField()
    user_agent = me.StringField()
    timestamp = me.DateTimeField(required=True, default=datetime.datetime.now)


class Requisition(me.Document):
    meta = {"collection": "requisitions"}

    requisition_code = me.StringField(max_length=50, unique=True, required=True)
    purchaser = me.ReferenceField("OrganizationUserRole", dbref=True, required=True)
    manager = me.ReferenceField("OrganizationUserRole", dbref=True)
    phone = me.StringField()
    reason = me.StringField(max_length=255)
    start_date = me.DateTimeField(required=True)
    tor_document = me.FileField(collection_name="tor_documents")
    qt_document = me.FileField(collection_name="qt_documents")

    # require at least 1 item and allow at most 4 items
    items = me.EmbeddedDocumentListField(
        "RequisitionItem", required=True, min_length=1, max_length=4
    )
    committees = me.EmbeddedDocumentListField("Committees")
    approval_history = me.EmbeddedDocumentListField("ApprovalHistory")

    status = me.StringField(default=STATUS_CHOICES[0][0])
    type = me.StringField(max_length=50)
    fund = me.ReferenceField("MAS", dbref=True)
    last_updated_by = me.ReferenceField("User", dbref=True)
    created_by = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )

    def save(self, *args, **kwargs):
        if not self.requisition_code:
            # ใช้ปี พ.ศ.
            now = datetime.datetime.now()
            buddhist_year = now.year + 543
            # หาเลขรันนิ้งล่าสุดของปีนี้
            prefix = f"{buddhist_year}-"
            last = (
                Requisition.objects(requisition_code__startswith=prefix)
                .order_by("-requisition_code")
                .first()
            )
            if last and last.requisition_code:
                last_number = int(last.requisition_code.split("-")[1])
                next_number = last_number + 1
            else:
                next_number = 1
            self.requisition_code = f"{buddhist_year}-{next_number:04d}"
        return super().save(*args, **kwargs)

    def get_category_display(self):
        # Return the display of the first item's category, or "-"
        if self.items and len(self.items) > 0:
            return self.items[0].get_category_display()
        return "-"
