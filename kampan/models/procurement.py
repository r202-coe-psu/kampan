"""ทะเบียนสัญญาบริการ (MA): หัวสัญญา (Procurement) → รายการย่อย (ProcurementItem) → งวด (Installment)

- หัวสัญญาเก็บเลขที่ ม.อ.เบิกจ่าย, ชื่อ, บริษัท และยอดเงินรวม
- รายการย่อยเก็บประเภท, ผังบัญชี, ช่วงวันที่, ยอดเงิน, ผู้รับผิดชอบ และงวด
- งวดไม่มีการแบ่งเงิน เป็นแค่ตัวช่วยจำว่าจ่ายไปแล้วกี่งวด (ยอดที่จ่ายจริงไม่บังคับ)
- ผลรวมยอดรายการย่อยต้องเท่ายอดรวมของหัว ตรวจใน ``Procurement.save_with_items``
"""

import datetime
import decimal
import logging
from collections.abc import Iterable

import mongoengine as me
from bson import ObjectId

logger = logging.getLogger(__name__)

CATEGORY_CHOICES = [
    ("material", "วัสดุ"),
    ("product", "ครุภัณฑ์"),
    ("service", "จ้างเหมาบริการ"),
    ("software", "ซอฟต์แวร์"),
]

# รายการย่อยของ MA มีประเภท "สินทรัพย์ไม่มีตัวตน" เพิ่ม (คำขอซื้อยังใช้ CATEGORY_CHOICES เดิม)
ITEM_CATEGORY_CHOICES = CATEGORY_CHOICES + [("intangible", "สินทรัพย์ไม่มีตัวตน")]

REMINDER_KIND_CHOICES = [
    ("ma", "MA"),
    ("license", "License"),
    ("rental", "เช่า-จ้างเหมา"),
]

# ผังบัญชี ใช้ร่วมกันระหว่างรายการย่อยของ MA และขั้นที่ 3 ของขอซื้อขอจ้าง
ACCOUNT_CODE_CHOICES = [
    ("12030201 อาคารและสิ่งปลูกสร้าง", "12030201 อาคารและสิ่งปลูกสร้าง"),
    ("12030203 ส่วนปรับปรุงอาคาร", "12030203 ส่วนปรับปรุงอาคาร"),
    ("12030302 ครุภัณฑ์", "12030302 ครุภัณฑ์"),
    (
        "12030402 งานระหว่างก่อสร้าง-ที่ดิน อาคาร และอุปกรณ์",
        "12030402 งานระหว่างก่อสร้าง-ที่ดิน อาคาร และอุปกรณ์",
    ),
    ("1204010101 สินทรัพย์ไม่มีตัวตน", "1204010101 สินทรัพย์ไม่มีตัวตน"),
    ("12070101 ถนน", "12070101 ถนน"),
    (
        "12070201 สินทรัพย์โครงสร้างพื้นฐานอื่น",
        "12070201 สินทรัพย์โครงสร้างพื้นฐานอื่น",
    ),
    (
        "12070302 งานระหว่างก่อสร้าง-สินทรัพย์โครงสร้างพื้นฐาน",
        "12070302 งานระหว่างก่อสร้าง-สินทรัพย์โครงสร้างพื้นฐาน",
    ),
    ("51010208 งานเบี้ยประกันสุขภาพ", "51010208 งานเบี้ยประกันสุขภาพ"),
    (
        "51040102 ค่าใช้จ่ายด้านฝึกอบรม-ในประเทศ",
        "51040102 ค่าใช้จ่ายด้านฝึกอบรม-ในประเทศ",
    ),
    (
        "51040105 ค่าใช้จ่ายด้านฝึกอบรมบุคคลภายนอก",
        "51040105 ค่าใช้จ่ายด้านฝึกอบรมบุคคลภายนอก",
    ),
    ("51040301 ค่าซ่อมแซมและค่าบำรุงรักษา", "51040301 ค่าซ่อมแซมและค่าบำรุงรักษา"),
    (
        "5104040101 ค่าจ้างเหมาบริการ-บุคคลภายนอก",
        "5104040101 ค่าจ้างเหมาบริการ-บุคคลภายนอก",
    ),
    ("51040601 ค่าจ้างที่ปรึกษา", "51040601 ค่าจ้างที่ปรึกษา"),
    ("51040701 ค่าเบี้ยประกันภัย", "51040701 ค่าเบี้ยประกันภัย"),
    ("51040901 ค่ารับรองและพิธีการ", "51040901 ค่ารับรองและพิธีการ"),
    (
        "51041002 ค่าเช่าอสังหาริมทรัพย์-บุคคลภายนอก",
        "51041002 ค่าเช่าอสังหาริมทรัพย์-บุคคลภายนอก",
    ),
    ("51041004 ค่าเช่าเบ็ดเตล็ด-บุคคลภายนอก", "51041004 ค่าเช่าเบ็ดเตล็ด-บุคคลภายนอก"),
    ("51041101 ค่าประชาสัมพันธ์", "51041101 ค่าประชาสัมพันธ์"),
    ("51041301 ค่าเชื้อเพลิง", "51041301 ค่าเชื้อเพลิง"),
    ("51041306 เงินชดเชยค่างานสิ่งก่อสร้าง", "51041306 เงินชดเชยค่างานสิ่งก่อสร้าง"),
    ("5104130804 ค่าใช้สอยอื่นๆ", "5104130804 ค่าใช้สอยอื่นๆ"),
    ("5105010101 ค่าวัสดุ", "5105010101 ค่าวัสดุ"),
    ("51050102 ค่าครุภัณฑ์ต่ำกว่าเกณฑ์", "51050102 ค่าครุภัณฑ์ต่ำกว่าเกณฑ์"),
    ("51060101 ค่าไฟฟ้า", "51060101 ค่าไฟฟ้า"),
]

PAYEMENT_STATUS_CHOICES = [
    ("unpaid", "ยังไม่ชำระเงิน"),
    ("overdue", "เลยกำหนดชำระ"),
    ("paid", "ชำระเงินแล้ว"),
    ("upcoming", "ใกล้ครบกำหนด"),
]

RENEWAL_STATUS_CHOICES = [
    ("pending", "รอดำเนินการ"),
    ("renewal-requested", "ยื่นขอต่ออายุ"),
    ("disactive", "ไม่อนุมัติ"),
    ("active", "จัดซื้อเรียบร้อย"),
    ("renewed", "ต่ออายุแล้ว"),
]

# งวดที่ครบกำหนดภายในกี่วันนับเป็น "ใกล้ครบกำหนด"
UPCOMING_DAYS = 7

# ใช้หาสถานะที่แย่ที่สุดของ MA จากทุกรายการย่อย
PAYMENT_STATUS_SEVERITY = {"paid": 0, "unpaid": 1, "upcoming": 2, "overdue": 3}


def _as_date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    return value


def _reference_id(document, field_name):
    """id ของ ReferenceField โดยไม่ dereference (ค่าดิบเป็น DBRef จนกว่าจะถูกอ่านผ่าน attribute)"""
    value = document._data.get(field_name)
    return getattr(value, "id", value)


def even_due_dates(start_date, end_date, count: int) -> list[datetime.date]:
    """วันครบกำหนด ``count`` งวดที่ห่างเท่า ๆ กันในช่วง start–end (งวดสุดท้ายตรงกับ end_date)

    ใช้เติมค่าเริ่มต้นของงวดเท่านั้น (ฟอร์มใช้สูตรเดียวกันใน JS) ผู้ใช้แก้วันเองได้
    """
    start = _as_date(start_date)
    end = _as_date(end_date)
    if not start or not end or not count or count < 1 or end < start:
        return []

    total_days = (end - start).days + 1  # รวมวันสุดท้าย
    days_per_period, remainder = divmod(total_days, count)

    due_dates = []
    current_start = start
    for index in range(count):
        days_this_period = days_per_period + (1 if index < remainder else 0)
        current_end = current_start + datetime.timedelta(days=max(days_this_period, 1) - 1)
        current_end = min(current_end, end)
        due_dates.append(current_end)
        current_start = current_end + datetime.timedelta(days=1)
    return due_dates


def check_item_sum(total_amount, amounts: Iterable) -> str | None:
    """ข้อความ error ถ้าผลรวมยอดรายการย่อยไม่เท่ายอดรวม MA (เทียบเท่ากันเป๊ะด้วย Decimal) ถ้าตรงคืน None"""
    # import ในฟังก์ชัน: kampan.utils import models กลับมา (circular import)
    from kampan.utils.money import money_sum, to_money

    total = to_money(total_amount)
    items_sum = money_sum(amounts)
    difference = items_sum - total
    if difference == 0:
        return None

    word = "ขาด" if difference < 0 else "เกิน"
    return (
        f"ผลรวมรายการย่อย {items_sum:,.2f} บาท ไม่ตรงกับยอด MA {total:,.2f} บาท "
        f"({word} {abs(difference):,.2f} บาท)"
    )


class RenewalConflict(Exception):
    """MA เดิมต่ออายุไปแล้ว หรือมีคำขออื่น claim ไปก่อน (เช่นกดบันทึกซ้ำ)"""


class Installment(me.EmbeddedDocument):
    """งวดของรายการย่อย ไม่มีการแบ่งเงิน มีแค่วันครบกำหนดและสถานะการจ่าย"""

    _id = me.ObjectIdField(required=True, default=ObjectId)
    due_date = me.DateTimeField(required=True)
    paid_date = me.DateTimeField()
    paid_by = me.ReferenceField("User", dbref=True)  # ผู้บันทึกการจ่าย
    payment_number = me.StringField(max_length=128)  # เลขที่เอกสาร / ใบจ่ายเงิน
    paid_amount = me.DecimalField(
        min_value=0,
        max_value=1e12,
        precision=2,
        rounding=decimal.ROUND_HALF_EVEN,
    )

    def is_paid(self) -> bool:
        return self.paid_date is not None

    def get_status(self, today: datetime.date | None = None) -> str:
        """paid / overdue (เลยวันครบกำหนด) / upcoming (เหลือ 0–7 วัน) / unpaid"""
        if self.is_paid():
            return "paid"
        today = today or datetime.date.today()
        due_date = _as_date(self.due_date)
        if not due_date:
            return "unpaid"
        days_left = (due_date - today).days
        if days_left < 0:
            return "overdue"
        if days_left <= UPCOMING_DAYS:
            return "upcoming"
        return "unpaid"


class ProcurementItem(me.Document):
    """รายการย่อยของ MA (collection แยก) ทุก query ต้อง scope ด้วย organization"""

    meta = {
        "collection": "procurement_items",
        "indexes": [
            "procurement",
            ("organization", "responsible_by"),
            ("organization", "responsible_divisions"),
            ("organization", "end_date"),
        ],
    }

    organization = me.ReferenceField("Organization", dbref=True, required=True)
    procurement = me.ReferenceField("Procurement", dbref=True, required=True)

    name = me.StringField(max_length=255, required=True)
    category = me.StringField(max_length=20, choices=ITEM_CATEGORY_CHOICES, required=True)
    account_code = me.StringField(max_length=200, choices=ACCOUNT_CODE_CHOICES)
    start_date = me.DateTimeField(required=True)
    end_date = me.DateTimeField(required=True)
    amount = me.DecimalField(
        required=True,
        min_value=0,
        max_value=1e12,
        precision=2,
        rounding=decimal.ROUND_HALF_EVEN,
    )
    # ข้อความอิสระ ใช้แทน S/N และรหัสครุภัณฑ์แบบแยกช่องเดิม
    details = me.StringField()

    # ช่องจากขั้นที่ 3 ของขอซื้อขอจ้างเดิม (#27) ผู้ชนะและราคาต่อหน่วยไม่บังคับ
    brand = me.StringField(max_length=100)
    model_name = me.StringField(max_length=100)
    winner = me.StringField(max_length=200)
    unit_price = me.DecimalField(
        min_value=0,
        max_value=1e12,
        precision=2,
        rounding=decimal.ROUND_HALF_EVEN,
    )
    note = me.StringField()

    responsible_by = me.ListField(me.ReferenceField("OrganizationUserRole", dbref=True))
    # คำนวณใหม่จาก responsible_by ทุกครั้งที่ save (ดู clean)
    responsible_divisions = me.ListField(me.ReferenceField("Division", dbref=True))

    reminder_kind = me.StringField(choices=REMINDER_KIND_CHOICES, default="ma", required=True)
    requires_activation = me.BooleanField(default=False)

    installments = me.EmbeddedDocumentListField(Installment)

    # Audit fields
    created_by = me.ReferenceField("User", dbref=True)
    last_updated_by = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(required=True, default=datetime.datetime.now, auto_now=True)

    def clean(self):
        if not self.installments:
            raise me.ValidationError("รายการย่อยต้องมีอย่างน้อย 1 งวด")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise me.ValidationError("วันที่สิ้นสุดต้องมากกว่าหรือเท่ากับวันที่เริ่มต้น")

        organization_id = getattr(self.organization, "id", None)
        divisions = []
        for member in self.responsible_by or []:
            if _reference_id(member, "organization") != organization_id:
                raise me.ValidationError("ผู้รับผิดชอบต้องเป็นสมาชิกของหน่วยงานเดียวกับ MA")
            division = member.division
            if division and all(division.id != existing.id for existing in divisions):
                divisions.append(division)
        self.responsible_divisions = divisions

    def get_category_label(self) -> str:
        return dict(ITEM_CATEGORY_CHOICES).get(self.category, self.category or "-")

    def get_reminder_kind_label(self) -> str:
        return dict(REMINDER_KIND_CHOICES).get(self.reminder_kind, self.reminder_kind or "-")

    def get_sorted_installments(self) -> list[Installment]:
        return sorted(self.installments, key=lambda installment: installment.due_date or datetime.datetime.max)

    def get_installment(self, installment_id) -> Installment | None:
        for installment in self.installments:
            if str(installment._id) == str(installment_id):
                return installment
        return None

    def get_next_unpaid_installment(self) -> Installment | None:
        """งวดที่ยังไม่จ่ายซึ่งครบกำหนดเร็วที่สุด"""
        unpaid = [installment for installment in self.installments if not installment.is_paid()]
        if not unpaid:
            return None
        return min(unpaid, key=lambda installment: installment.due_date or datetime.datetime.max)

    def get_paid_count(self) -> int:
        return sum(1 for installment in self.installments if installment.is_paid())

    def get_payment_status(self, today: datetime.date | None = None) -> str:
        """สถานะของงวดที่ยังไม่จ่ายซึ่งครบกำหนดเร็วสุด (แย่สุดของรายการนี้) หรือ paid เมื่อจ่ายครบ"""
        next_installment = self.get_next_unpaid_installment()
        if not next_installment:
            return "paid" if self.installments else "unpaid"
        return next_installment.get_status(today)

    def get_responsible_ids(self) -> set:
        return {getattr(member, "id", member) for member in self._data.get("responsible_by") or []}


class Procurement(me.Document):
    """หัวสัญญา MA (collection procurements เดิม)"""

    meta = {
        "collection": "procurements",
        # เอกสารรูปแบบเก่าที่ยังหลงเหลือ (มี field ที่ถูกลบไปแล้ว) ต้องไม่ทำให้หน้าเว็บ 500
        "strict": False,
        "indexes": [
            ("organization", "psu_disbursement_number"),
            ("organization", "status"),
        ],
    }

    image = me.ImageField()
    # บังคับในฟอร์ม แต่ไม่บังคับใน model และซ้ำได้
    psu_disbursement_number = me.StringField(max_length=128)
    name = me.StringField(max_length=255, required=True)
    company = me.StringField(max_length=255, required=True)
    total_amount = me.DecimalField(
        required=True,
        min_value=0,
        max_value=1e12,
        precision=2,
        rounding=decimal.ROUND_HALF_EVEN,
    )
    # status: สถานะการต่ออายุ (renewal process)
    status = me.StringField(choices=RENEWAL_STATUS_CHOICES, default="active")

    organization = me.ReferenceField("Organization", dbref=True, required=True)

    # การต่ออายุ (#32): MA ใหม่ชี้ MA เดิม และ MA เดิมชี้ MA ใหม่
    renewed_from = me.ReferenceField("Procurement", dbref=True)
    renewed_to = me.ReferenceField("Procurement", dbref=True)
    # สถานะก่อนถูก claim เพื่อต่ออายุ ใช้คืนสถานะเมื่อสร้าง MA ใหม่ไม่สำเร็จ
    # (status = renewed แต่ยังไม่มี renewed_to คือกำลังต่ออายุอยู่)
    status_before_renewal = me.StringField(choices=RENEWAL_STATUS_CHOICES)

    # Audit fields
    last_updated_by = me.ReferenceField("User", dbref=True)
    created_by = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(required=True, default=datetime.datetime.now, auto_now=True)

    def is_renewed(self) -> bool:
        return self.status == "renewed" or _reference_id(self, "renewed_to") is not None

    # ------------------------------------------------------------------
    # รายการย่อย
    # ------------------------------------------------------------------

    def get_items(self) -> list[ProcurementItem]:
        """รายการย่อยเรียงตามลำดับที่สร้าง (cache ไว้ในตัวเอกสาร ดู attach_items)"""
        cached = self.__dict__.get("_items_cache")
        if cached is None:
            if not self.pk:
                return []
            cached = list(
                ProcurementItem.objects(procurement=self, organization=self.organization).order_by("id")
            )
            self.__dict__["_items_cache"] = cached
        return cached

    def get_payment_status(self, today: datetime.date | None = None) -> str:
        """สถานะที่แย่ที่สุดของทุกรายการย่อย (overdue > upcoming > unpaid) หรือ paid เมื่อจ่ายครบทุกงวด"""
        statuses = [item.get_payment_status(today) for item in self.get_items()]
        if not statuses:
            return "unpaid"
        return max(statuses, key=lambda status: PAYMENT_STATUS_SEVERITY.get(status, 0))

    def get_installment_progress(self) -> tuple[int, int]:
        """(จำนวนงวดที่จ่ายแล้ว, จำนวนงวดทั้งหมด) ของทุกรายการย่อย"""
        items = self.get_items()
        return (
            sum(item.get_paid_count() for item in items),
            sum(len(item.installments) for item in items),
        )

    def get_next_unpaid(self) -> tuple[ProcurementItem | None, Installment | None]:
        """งวดที่ยังไม่จ่ายซึ่งครบกำหนดเร็วที่สุดของทั้ง MA"""
        candidates = [(item, item.get_next_unpaid_installment()) for item in self.get_items()]
        candidates = [(item, installment) for item, installment in candidates if installment]
        if not candidates:
            return None, None
        return min(candidates, key=lambda pair: pair[1].due_date or datetime.datetime.max)

    def get_start_date(self):
        dates = [item.start_date for item in self.get_items() if item.start_date]
        return min(dates) if dates else None

    def get_end_date(self):
        """วันสิ้นสุดของรายการย่อยที่หมดอายุก่อน ใช้กับการต่ออายุและการเรียงตามวันหมดอายุ"""
        dates = [item.end_date for item in self.get_items() if item.end_date]
        return min(dates) if dates else None

    def get_responsible_members(self) -> list:
        members = []
        seen = set()
        for item in self.get_items():
            for member in item.responsible_by or []:
                member_id = getattr(member, "id", None)
                if member_id and member_id not in seen:
                    seen.add(member_id)
                    members.append(member)
        return members

    def get_responsible_divisions(self) -> list:
        divisions = []
        seen = set()
        for item in self.get_items():
            for division in item.responsible_divisions or []:
                division_id = getattr(division, "id", None)
                if division_id and division_id not in seen:
                    seen.add(division_id)
                    divisions.append(division)
        return divisions

    def get_version(self) -> str:
        """เวลาแก้ไขล่าสุดของหัวและทุกรายการย่อย ใช้กันฟอร์มแก้ไขที่ค้างข้อมูลเก่าเขียนทับ"""
        dates = [self.updated_date] + [item.updated_date for item in self.get_items()]
        return max(date for date in dates if date).isoformat(timespec="milliseconds")

    def get_category_labels(self) -> list[str]:
        labels = []
        for item in self.get_items():
            label = item.get_category_label()
            if label not in labels:
                labels.append(label)
        return labels

    # ------------------------------------------------------------------
    # บันทึกหัว + รายการย่อย
    # ------------------------------------------------------------------

    def save_with_items(self, items: Iterable[ProcurementItem], removed_items: Iterable[ProcurementItem] = ()):
        """ทางบันทึกเดียวของ MA (สร้าง, แก้ไข, นำเข้า Excel และต่ออายุ)

        - ตรวจผลรวมยอด หัว และทุกรายการย่อยก่อนเขียนเอกสารใด ๆ ถ้าไม่ผ่าน raise ValidationError
        - เขียนหัว → รายการย่อย → ลบรายการที่ถูกเอาออก ถ้าเขียนไม่สำเร็จกลางทาง คืนข้อมูลเดิมแล้ว raise ต่อ
        """
        items = list(items)
        removed_items = [item for item in removed_items if item.pk]
        if not items:
            raise me.ValidationError("MA ต้องมีรายการย่อยอย่างน้อย 1 รายการ")

        sum_error = check_item_sum(self.total_amount, (item.amount for item in items))
        if sum_error:
            raise me.ValidationError(sum_error)

        is_new = self.pk is None
        if is_new:
            # ตั้ง id ก่อน รายการย่อยจึง validate ReferenceField ได้ทั้งที่ยังไม่ได้เขียนหัว
            self.id = ObjectId()

        # auto_now ของ DateTimeField ไม่มีผลใน MongoEngine จึงตั้งเวลาแก้ไขเอง (ใช้ตรวจการแก้ไขชนกันด้วย)
        now = datetime.datetime.now()
        self.updated_date = now
        for item in items:
            item.procurement = self
            item.organization = self.organization
            item.updated_date = now

        try:
            self.validate()
            for item in items:
                item.validate()
        except me.ValidationError:
            if is_new:
                self.id = None
            raise

        snapshot = self._snapshot(items, removed_items, is_new)
        written_items = []
        try:
            self.save(force_insert=is_new, validate=False)
            for item in items:
                item.save(validate=False)
                written_items.append(item)
            for item in removed_items:
                item.delete()
        except Exception:
            logger.exception("save_with_items failed for procurement %s, restoring", self.pk)
            self._restore(snapshot, written_items, is_new)
            raise

        self.__dict__["_items_cache"] = items
        return self

    def renew_into(self, new_procurement: "Procurement", items: Iterable[ProcurementItem]) -> "Procurement":
        """ต่ออายุ MA นี้เป็น ``new_procurement`` (#32)

        1. claim MA นี้แบบ atomic ก่อน (ยังไม่ต่ออายุ → status renewed) กันกดบันทึกซ้ำได้ MA ใหม่ 2 ตัว
           ถ้า claim ไม่ได้ raise RenewalConflict
        2. สร้าง MA ใหม่ผ่าน save_with_items (renewed_from ชี้ MA นี้)
        3. ผูก renewed_to ของ MA นี้ไปที่ MA ใหม่
        ถ้าข้อ 2–3 ล้ม ลบ MA ใหม่ที่เขียนไปแล้ว คืน claim แล้ว raise ต่อ (ValidationError ของข้อ 2 ใช้แสดงในฟอร์มได้)
        """
        previous_status = self.status
        if previous_status == "renewed":
            raise RenewalConflict()
        # เงื่อนไข status เดิม: ถ้ามีคนเปลี่ยนสถานะ (รวมถึง claim ไปก่อน) หลังเราโหลด MA จะ claim ไม่ได้
        claimed = Procurement.objects(
            id=self.pk,
            organization=self.organization,
            status=previous_status,
            renewed_to=None,
        ).update_one(
            set__status="renewed",
            set__status_before_renewal=previous_status,
            set__updated_date=datetime.datetime.now(),
        )
        if not claimed:
            raise RenewalConflict()

        new_procurement.organization = self.organization
        new_procurement.renewed_from = self
        try:
            new_procurement.save_with_items(items)
            linked = Procurement.objects(id=self.pk, organization=self.organization, renewed_to=None).update_one(
                set__renewed_to=new_procurement
            )
            if not linked:
                raise RenewalConflict()
        except Exception:
            logger.exception("renewing procurement %s failed, releasing the claim", self.pk)
            self._discard_renewal(new_procurement, previous_status)
            raise

        self.status = "renewed"
        self.status_before_renewal = previous_status
        self.renewed_to = new_procurement
        return new_procurement

    def _discard_renewal(self, new_procurement, previous_status):
        try:
            if new_procurement.pk and Procurement.objects(id=new_procurement.pk).count():
                ProcurementItem.objects(procurement=new_procurement.pk).delete()
                Procurement.objects(id=new_procurement.pk).delete()
            Procurement.objects(id=self.pk, organization=self.organization, status="renewed", renewed_to=None).update_one(
                set__status=previous_status,
                unset__status_before_renewal=True,
            )
        except Exception:
            logger.exception("releasing the renewal claim of procurement %s failed", self.pk)

    def get_renewal_chain(self) -> list["Procurement"]:
        """สายการต่ออายุทั้งหมดที่ MA นี้อยู่ เรียงจาก MA แรกสุดไปล่าสุด (เดินตาม renewed_from / renewed_to ในหน่วยงานเดียวกัน)"""
        chain = [self]
        seen = {self.pk}

        current = self
        while True:
            previous_id = _reference_id(current, "renewed_from")
            if not previous_id or previous_id in seen:
                break
            current = Procurement.objects(id=previous_id, organization=self.organization).first()
            if not current:
                break
            seen.add(current.pk)
            chain.insert(0, current)

        current = self
        while True:
            next_id = _reference_id(current, "renewed_to")
            if not next_id or next_id in seen:
                break
            current = Procurement.objects(id=next_id, organization=self.organization).first()
            if not current:
                break
            seen.add(current.pk)
            chain.append(current)
        return chain

    def _snapshot(self, items, removed_items, is_new) -> dict:
        if is_new:
            return {}
        item_ids = [item.pk for item in list(items) + list(removed_items) if item.pk]
        return {
            "procurement": self._get_collection().find_one({"_id": self.pk}),
            "items": list(ProcurementItem._get_collection().find({"_id": {"$in": item_ids}})),
        }

    def _restore(self, snapshot, written_items, is_new):
        items_collection = ProcurementItem._get_collection()
        try:
            if is_new:
                for item in written_items:
                    items_collection.delete_one({"_id": item.pk})
                self._get_collection().delete_one({"_id": self.pk})
                return

            known_ids = {raw["_id"] for raw in snapshot["items"]}
            for item in written_items:
                if item.pk not in known_ids:
                    items_collection.delete_one({"_id": item.pk})
            for raw in snapshot["items"]:
                items_collection.replace_one({"_id": raw["_id"]}, raw, upsert=True)
            if snapshot["procurement"]:
                self._get_collection().replace_one({"_id": self.pk}, snapshot["procurement"])
        except Exception:
            logger.exception("restore after failed save_with_items failed for procurement %s", self.pk)


def attach_items(procurements: Iterable[Procurement], organization) -> list[Procurement]:
    """โหลดรายการย่อยของหลาย MA ด้วย query เดียว แล้ว cache ไว้ใน MA แต่ละตัว (กัน N+1 ในหน้ารายการ)"""
    procurements = list(procurements)
    by_id = {procurement.pk: [] for procurement in procurements}
    if by_id:
        items = ProcurementItem.objects(organization=organization, procurement__in=list(by_id)).order_by("id")
        for item in items:
            procurement_id = _reference_id(item, "procurement")
            if procurement_id in by_id:
                by_id[procurement_id].append(item)
    for procurement in procurements:
        procurement.__dict__["_items_cache"] = by_id[procurement.pk]
    return procurements


def procurement_ids_of(item_queryset) -> list:
    """id ของหัวสัญญาจาก queryset ของ ProcurementItem (ไม่ dereference ทีละตัว)"""
    ids = []
    seen = set()
    for item in item_queryset.only("procurement"):
        procurement_id = _reference_id(item, "procurement")
        if procurement_id not in seen:
            seen.add(procurement_id)
            ids.append(procurement_id)
    return ids
