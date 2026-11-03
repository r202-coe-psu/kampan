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
    ("pending", "รอดำเนินการ"),
    ("progress", "กําลังดําเนินการ"),
    ("complete", "อนุมัติ"),
    ("cancelled", "ยกเลิก"),
]

# ลำดับขั้นการอนุมัติ: หัวหน้าฝ่าย → เจ้าหน้าที่พัสดุ → ผู้บริหาร
APPROVAL_STEPS = ("head", "admin", "manager")
APPROVAL_ACTIONS = ("approved", "rejected")
APPROVAL_CLOSED_STATUSES = ("incomplete", "complete", "completed", "cancelled")

SHOW_ITEM_CHOICES = [
    ("all", "แสดงทั้งหมด"),
    ("me", "แสดงเฉพาะของฉัน"),
]

FUND_CHOICES = [
    ("budget", "เงินงบประมาณ"),
    ("income_institute", "เงินรายได้สานักฯ"),
    ("income_central_university", "เงินรายได้ส่วนกลางมหาวิทยาลัย"),
    ("income_sno", "เงินรายได้ สนอ."),
    ("income_central_smartu", "เงินรายได้ส่วนกลาง (Smart U)"),
]


class Funds(me.EmbeddedDocument):
    mas = me.ReferenceField("MAS", dbref=True)
    reservation = me.ReferenceField("Reservation", dbref=True)
    amount = me.DecimalField(required=True, min_value=0, max_value=1e12, precision=2)
    assigned_by = me.ReferenceField("User", dbref=True)
    assigned_date = me.DateTimeField(required=True, default=datetime.datetime.now)


class Committees(me.EmbeddedDocument):
    _id = me.ObjectIdField(required=True, default=ObjectId)
    member = me.ReferenceField("OrganizationUserRole", dbref=True)
    committee_type = me.StringField(max_length=50, required=True)
    committee_position = me.StringField(max_length=50, required=True)


class RequisitionItem(me.EmbeddedDocument):
    _id = me.ObjectIdField(required=True, default=ObjectId)
    product_name = me.StringField(max_length=100, required=True)
    company = me.StringField(max_length=100)
    quantity = me.IntField(min_value=1, required=True)
    category = me.StringField(max_length=20, choices=CATEGORY_CHOICES, required=True)
    amount = me.DecimalField(required=True, min_value=0, max_value=1e12, precision=2)
    currency = me.StringField(max_length=10)
    brand = me.StringField(max_length=100)
    model_name = me.StringField(max_length=100)
    winner = me.StringField(max_length=200)
    account_code = me.StringField(max_length=100)
    note = me.StringField()


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


class SelectedManager(me.EmbeddedDocument):
    manager = me.ReferenceField("OrganizationUserRole", dbref=True)
    is_acting = me.BooleanField(default=False)  # รักษาการหรือไม่


class Requisition(me.Document):
    meta = {"collection": "requisitions"}

    requisition_code = me.StringField(max_length=50, unique=True, required=True)
    organization = me.ReferenceField("Organization", dbref=True, required=True)
    project_name = me.StringField(max_length=255)
    purchaser = me.ReferenceField("OrganizationUserRole", dbref=True, required=True)
    selected_manager = me.EmbeddedDocumentField(SelectedManager)
    phone = me.StringField()
    reason = me.StringField()
    start_date = me.DateTimeField(required=True)
    tor_document = me.FileField(collection_name="tor_documents")
    qt_document = me.FileField(collection_name="qt_documents")

    # require at least 1 item and allow at most 4 items
    items = me.EmbeddedDocumentListField("RequisitionItem", required=True, min_length=1, max_length=4)
    committees = me.EmbeddedDocumentListField("Committees")
    approval_history = me.EmbeddedDocumentListField("ApprovalHistory")
    fund_source = me.StringField(max_length=255)

    status = me.StringField(default=STATUS_CHOICES[0][0])
    type = me.StringField(max_length=50)
    fund = me.EmbeddedDocumentListField("Funds")
    last_updated_by = me.ReferenceField("User", dbref=True)
    created_by = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(required=True, default=datetime.datetime.now, auto_now=True)

    def save(self, *args, **kwargs):
        if not self.requisition_code:
            # ใช้ปี พ.ศ.
            now = datetime.datetime.now()
            buddhist_year = now.year + 543
            # หาเลขรันนิ้งล่าสุดของปีนี้
            suffix = f"/{buddhist_year}"
            last = Requisition.objects(requisition_code__endswith=suffix).order_by("-requisition_code").first()
            if last and last.requisition_code:
                last_number = int(last.requisition_code.split("/")[0])
                next_number = last_number + 1
            else:
                next_number = 1
            self.requisition_code = f"{next_number:03d}/{buddhist_year}"
        return super().save(*args, **kwargs)

    def get_category_display(self):
        # Return the display of the first item's category, or "-"
        if self.items and len(self.items) > 0:
            return self.items[0].get_category_display()
        return "-"

    def get_approval(self, approver_role: str):
        for approval in self.approval_history or []:
            if approval.approver_role == approver_role:
                return approval
        return None

    def get_approval_error(self, approver_role: str, user) -> str | None:
        """คืนเหตุผลที่ user ดำเนินการขั้น approver_role ไม่ได้ หรือ None ถ้าดำเนินการได้

        ใช้ทั้งฝั่ง server (requisition_action) และ template เพื่อให้กติกาตรงกัน
        global admin ดำเนินการแทนได้ทุกขั้น แต่ยังต้องเรียงลำดับขั้น
        """
        from .organizations import OrganizationUserRole

        if approver_role not in APPROVAL_STEPS:
            return "ขั้นการอนุมัติไม่ถูกต้อง"
        if self.status in APPROVAL_CLOSED_STATUSES:
            return "รายการนี้ปิดการอนุมัติแล้ว"
        if self.get_approval(approver_role):
            return "ขั้นนี้ดำเนินการแล้ว"

        step_index = APPROVAL_STEPS.index(approver_role)
        if step_index > 0:
            previous = self.get_approval(APPROVAL_STEPS[step_index - 1])
            if not previous or previous.action != "approved":
                return "รอการอนุมัติจากขั้นก่อนหน้า"

        if "admin" in user.roles:
            return None

        # template ส่ง current_user (LocalProxy) มา ต้องแปลงเป็น User ก่อนใช้ใน query
        user = getattr(user, "_get_current_object", lambda: user)()
        member = OrganizationUserRole.objects(
            user=user, organization=self.organization, status__ne="disactive"
        ).first()
        if not member:
            return "ไม่มีสิทธิ์ดำเนินการขั้นนี้"

        if approver_role == "head":
            if "head" not in member.roles:
                return "ไม่มีสิทธิ์ดำเนินการขั้นนี้"
            purchaser_division = self.purchaser.division if self.purchaser else None
            if not member.division or purchaser_division != member.division:
                return "อนุมัติได้เฉพาะคำขอของฝ่ายตัวเอง"
        elif approver_role == "admin":
            if "admin" not in member.roles:
                return "ไม่มีสิทธิ์ดำเนินการขั้นนี้"
        elif approver_role == "manager":
            selected = self.selected_manager.manager if self.selected_manager else None
            if selected != member:
                return "อนุมัติได้เฉพาะผู้บริหารที่ถูกเลือก"

        return None
