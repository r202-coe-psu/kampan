"""ทะเบียนสัญญาบริการ (MA): หัวสัญญา (Procurement) → รายการย่อย (ProcurementItem) → งวด (Installment)

- หัวสัญญาเก็บเลขที่ ม.อ.เบิกจ่าย, ชื่อ, บริษัท และยอดเงินรวม
- รายการย่อยเก็บประเภท, ผังบัญชี, ช่วงวันที่, ยอดเงิน, ผู้รับผิดชอบ และงวด
- งวดไม่มีการแบ่งเงิน เป็นแค่ตัวช่วยจำว่าจ่ายไปแล้วกี่งวด (ยอดที่จ่ายจริงไม่บังคับ)
- ผลรวมยอดรายการย่อยต้องเท่ายอดรวมของหัว ตรวจใน ``Procurement.save_with_items``
"""

import datetime
import decimal
import logging
import re
from collections.abc import Iterable

import mongoengine as me
from bson import ObjectId

from .divisions import Division
from .organizations import OrganizationUserRole
from .users import User

logger = logging.getLogger(__name__)

CATEGORY_CHOICES = [
    ("material", "วัสดุ"),
    ("product", "ครุภัณฑ์"),
    ("service", "จ้างเหมาบริการ"),
    ("software", "ซอฟต์แวร์"),
]

# ตัวเลือกประเภทรายการ MA ในแบบฟอร์มและตัวกรอง เรียงตามที่ใช้งาน (ไม่มี "วัสดุ"):
# การบำรุงรักษา (MA) / จ้างเหมาบริการ / ซอฟต์แวร์ / สินทรัพย์ไม่มีตัวตน / ครุภัณฑ์ / เช่า
MA_CATEGORY_CHOICES = [
    ("ma", "การบำรุงรักษา (MA)"),
    ("service", "จ้างเหมาบริการ"),
    ("software", "ซอฟต์แวร์"),
    ("intangible", "สินทรัพย์ไม่มีตัวตน"),
    ("product", "ครุภัณฑ์"),
    ("rental", "เช่า"),
]

# รวมทุกประเภทที่ระบบเคยรองรับ เพื่ออ่านข้อมูลเดิม (เช่น "วัสดุ") และแสดงป้ายได้ ไม่ใช้เป็นตัวเลือกในฟอร์ม
ITEM_CATEGORY_CHOICES = MA_CATEGORY_CHOICES + [
    ("material", "วัสดุ"),
]

REMINDER_KIND_CHOICES = [
    ("ma", "MA"),
    ("license", "License"),
    ("rental", "เช่า-จ้างเหมา"),
]

# ช่วงเตือนล่วงหน้าที่เลือกได้ (#28) ใช้ทั้งเตือนหมดอายุ (ก่อน end_date) และเตือนจ่ายงวด (ก่อน due_date)
REMINDER_OFFSET_CHOICES = [
    ("6m", "180 วัน"),
    ("5m", "150 วัน"),
    ("4m", "120 วัน"),
    ("3m", "90 วัน"),
    ("2m", "60 วัน"),
    ("1m", "30 วัน"),
    ("15d", "15 วัน"),
    ("7d", "7 วัน"),
]
DEFAULT_REMINDER_OFFSETS = ["3m", "2m", "1m", "15d", "7d"]
# เตือนจ่ายงวด: เตือนในวันครบกำหนดเสมอ (ไม่เก็บเป็นตัวเลือก) และเพิ่ม 7, 5, 3 วันก่อนวันครบกำหนดได้ (ค่าเริ่มต้นไม่ติ๊ก)
PAYMENT_REMINDER_OFFSET_CHOICES = [
    ("7d", "7 วัน"),
    ("5d", "5 วัน"),
    ("3d", "3 วัน"),
]
DEFAULT_PAYMENT_REMINDER_OFFSETS: list[str] = []
# ค่าที่เก็บเดิม (เช่น 3m, 15d) ยังอ่านได้ แต่ไม่ถูกใช้ส่งเตือนจ่ายงวด
ALL_PAYMENT_OFFSET_CHOICES = PAYMENT_REMINDER_OFFSET_CHOICES + REMINDER_OFFSET_CHOICES
# จำนวนวันเตือนที่กรอกเอง (#29)
MAX_REMINDER_OFFSET_DAYS = 730
# จำนวนงวดสูงสุดต่อรายการย่อย (ฟอร์มและนำเข้า Excel)
MAX_INSTALLMENTS_PER_ITEM = 120
MAX_SUB_ITEMS_PER_ITEM = 100
MAX_SUB_ITEMS_MESSAGE = f"จำนวนแถวยี่ห้อ / รุ่น / รายละเอียดต้องไม่เกิน {MAX_SUB_ITEMS_PER_ITEM} แถว"
MAX_INSTALLMENTS_MESSAGE = f"จำนวนงวดต้องไม่เกิน {MAX_INSTALLMENTS_PER_ITEM}"


def default_reminder_offsets() -> list[str]:
    return list(DEFAULT_REMINDER_OFFSETS)


def default_payment_reminder_offsets() -> list[str]:
    return list(DEFAULT_PAYMENT_REMINDER_OFFSETS)


# ผังบัญชี 15 รายการตามแบบฟอร์มเพิ่มรายการ MA
ACCOUNT_CODE_CHOICES = [
    ("12030201 อาคารและสิ่งปลูกสร้าง", "12030201 อาคารและสิ่งปลูกสร้าง"),
    ("12030203 ส่วนปรับปรุงอาคาร", "12030203 ส่วนปรับปรุงอาคาร"),
    ("12030302 ครุภัณฑ์", "12030302 ครุภัณฑ์"),
    (
        "12030402 งานระหว่างก่อสร้าง-ที่ดิน อาคาร และอุปกรณ์",
        "12030402 งานระหว่างก่อสร้าง-ที่ดิน อาคาร และอุปกรณ์",
    ),
    ("1204010101 สินทรัพย์ไม่มีตัวตน", "1204010101 สินทรัพย์ไม่มีตัวตน"),
    ("51040301 ค่าซ่อมแซมและค่าบำรุงรักษา", "51040301 ค่าซ่อมแซมและค่าบำรุงรักษา"),
    (
        "5104040101 ค่าจ้างเหมาบริการ-บุคคลภายนอก",
        "5104040101 ค่าจ้างเหมาบริการ-บุคคลภายนอก",
    ),
    ("51040701 ค่าเบี้ยประกันภัย", "51040701 ค่าเบี้ยประกันภัย"),
    ("51041004 ค่าเช่าเบ็ดเตล็ด-บุคคลภายนอก", "51041004 ค่าเช่าเบ็ดเตล็ด-บุคคลภายนอก"),
    ("51041101 ค่าประชาสัมพันธ์", "51041101 ค่าประชาสัมพันธ์"),
    ("51041301 ค่าเชื้อเพลิง", "51041301 ค่าเชื้อเพลิง"),
    ("5104130804 ค่าใช้สอยอื่นๆ", "5104130804 ค่าใช้สอยอื่นๆ"),
    ("5105010101 ค่าวัสดุ", "5105010101 ค่าวัสดุ"),
    ("51050102 ค่าครุภัณฑ์ต่ำกว่าเกณฑ์", "51050102 ค่าครุภัณฑ์ต่ำกว่าเกณฑ์"),
    ("51060104 ค่าบริการสื่อสารและโทรคมนาคม", "51060104 ค่าบริการสื่อสารและโทรคมนาคม"),
]

LEGACY_ACCOUNT_CODE_CHOICES = [
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
    ("51040601 ค่าจ้างที่ปรึกษา", "51040601 ค่าจ้างที่ปรึกษา"),
    ("51040901 ค่ารับรองและพิธีการ", "51040901 ค่ารับรองและพิธีการ"),
    (
        "51041002 ค่าเช่าอสังหาริมทรัพย์-บุคคลภายนอก",
        "51041002 ค่าเช่าอสังหาริมทรัพย์-บุคคลภายนอก",
    ),
    ("51041306 เงินชดเชยค่างานสิ่งก่อสร้าง", "51041306 เงินชดเชยค่างานสิ่งก่อสร้าง"),
    ("51060101 ค่าไฟฟ้า", "51060101 ค่าไฟฟ้า"),
]

ALL_ACCOUNT_CODE_CHOICES = ACCOUNT_CODE_CHOICES + LEGACY_ACCOUNT_CODE_CHOICES

PAYEMENT_STATUS_CHOICES = [
    ("unpaid", "ยังไม่ชำระเงิน"),
    ("overdue", "เลยกำหนดชำระ"),
    ("paid", "ชำระเงินแล้ว"),
    ("upcoming", "ใกล้ครบกำหนด"),
]

# สถานะการต่ออายุ (field ``status``): review → renewal-requested → renewed / disactive
# ``active`` / ``pending`` เป็นค่าเดิมที่ยังอ่านได้ (= review) ไม่ใช้เขียนใหม่ ดู normalize_renewal_status
RENEWAL_STATUS_CHOICES = [
    ("draft", "แบบร่าง"),
    ("review", "รอตรวจสอบ"),
    ("renewal-requested", "รอต่ออายุ"),
    ("renewed", "ต่ออายุแล้ว"),
    ("disactive", "ไม่ต่ออายุ"),
    ("active", "รอตรวจสอบ"),
    ("pending", "รอตรวจสอบ"),
]
LEGACY_REVIEW_STATUSES = ("active", "pending")
# ค่า status ทั้งหมดที่นับเป็น "รอตรวจสอบ" (ใช้กรอง queryset)
REVIEW_STATUSES = ("review",) + LEGACY_REVIEW_STATUSES

# สิ่งที่ผู้รับผิดชอบขอ (field ``renewal_request``)
RENEWAL_REQUEST_CHOICES = [
    ("renew", "ขอต่ออายุ"),
    ("stop", "ขอไม่ต่ออายุ"),
]

# สถานะการใช้งาน (field ``usage_status``) คำนวณจากวันเริ่ม / สิ้นสุดของรายการย่อย
USAGE_STATUS_CHOICES = [
    ("upcoming", "รอดำเนินการ"),
    ("in_use", "กำลังใช้งาน"),
    ("expired", "หมดอายุ"),
]


def normalize_renewal_status(status: str | None) -> str | None:
    """ค่าเดิม active / pending อ่านเป็น review"""
    return "review" if status in LEGACY_REVIEW_STATUSES else status


def renewal_status_statuses(status: str | None) -> list[str]:
    """ค่า status ที่เก็บได้ทั้งหมดของสถานะการต่ออายุหนึ่ง (review รวมค่าเดิม) ใช้เป็นเงื่อนไข query"""
    if status == "review":
        return list(REVIEW_STATUSES)
    return [status] if status else []


def compute_usage_status(start_date, end_date, today: datetime.date | None = None) -> str | None:
    """upcoming = วันนี้ก่อนวันเริ่มแรกสุด · expired = วันนี้หลังวันสิ้นสุดสุดท้าย · in_use = ช่วงระหว่างนั้น
    ไม่มีวันที่ใดเลยคืน None"""
    start, end = _as_date(start_date), _as_date(end_date)
    if not start and not end:
        return None
    today = today or datetime.date.today()
    if start and today < start:
        return "upcoming"
    if end and today > end:
        return "expired"
    return "in_use"

# งวดที่ครบกำหนดภายในกี่วันนับเป็น "ใกล้ครบกำหนด"
UPCOMING_DAYS = 30

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


def _reference_ids(document, field_name) -> list:
    """id ของ ListField(ReferenceField) ตามลำดับเดิม โดยไม่ dereference"""
    return [getattr(value, "id", value) for value in document._data.get(field_name) or []]


def installment_status(due_date, paid_date, today: datetime.date | None = None) -> str:
    """paid / overdue (เลยวันครบกำหนด) / upcoming (เหลือ 0–30 วัน) / unpaid"""
    if paid_date is not None:
        return "paid"
    today = today or datetime.date.today()
    due_date = _as_date(due_date)
    if not due_date:
        return "unpaid"
    days_left = (due_date - today).days
    if days_left < 0:
        return "overdue"
    if days_left <= UPCOMING_DAYS:
        return "upcoming"
    return "unpaid"


def item_payment_status(installments: Iterable[tuple], today: datetime.date | None = None) -> str:
    """สถานะของรายการย่อยจากงวด ``(due_date, paid_date)``: งวดที่ยังไม่จ่ายซึ่งครบกำหนดเร็วสุด หรือ paid เมื่อจ่ายครบ"""
    installments = list(installments)
    unpaid_due_dates = [due_date for due_date, paid_date in installments if paid_date is None]
    if not unpaid_due_dates:
        return "paid" if installments else "unpaid"
    next_due_date = min(unpaid_due_dates, key=lambda due_date: due_date or datetime.datetime.max)
    return installment_status(next_due_date, None, today)


def worst_payment_status(statuses: Iterable[str]) -> str:
    """สถานะที่แย่ที่สุด (overdue > upcoming > unpaid > paid) ไม่มีรายการย่อยถือว่า unpaid
    รายการที่ไม่แบ่งจ่ายเป็นงวดจ่ายแล้วตอนสร้าง MA (paid) จึงไม่ทำให้สถานะของ MA แย่ลง"""
    return max(statuses, key=lambda status: PAYMENT_STATUS_SEVERITY.get(status, 0), default="unpaid")


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


class ItemDeleteError(Exception):
    """ลบรายการย่อยไม่ได้ (จ่ายงวดแล้ว / เป็นรายการสุดท้าย) ข้อความใช้แสดงผู้ใช้"""


class ConcurrentEditConflict(Exception):
    """หัวหรือรายการย่อยถูกแก้ / บันทึกจ่ายงวดโดยผู้อื่นหลังจากโหลดมา จึงไม่เขียนทับ"""


PAY_LOG_ACTIONS = [
    ("paid", "บันทึกจ่าย"),
    ("edited", "แก้ไขการบันทึก"),
    ("unpaid", "ยกเลิกการจ่าย"),
    ("renewed", "จ่ายตอนต่ออายุ"),
]


class PayLogEntry(me.EmbeddedDocument):
    """ประวัติการกดจ่าย / ยกเลิกจ่ายของงวด (เพิ่มทุกครั้งที่กด ไม่แก้ไม่ลบ)"""

    action = me.StringField(choices=PAY_LOG_ACTIONS, required=True)
    pressed_at = me.DateTimeField(required=True, default=datetime.datetime.now)  # เวลาที่กดปุ่ม
    # วันที่จ่ายที่บันทึก (action=unpaid: วันที่จ่ายเดิมที่ถูกยกเลิก)
    paid_date = me.DateTimeField()
    by = me.ReferenceField("User", dbref=True)
    payment_number = me.StringField(max_length=128)
    paid_amount = me.DecimalField(
        min_value=0,
        max_value=1e12,
        precision=2,
        rounding=decimal.ROUND_HALF_EVEN,
    )

    def get_by_id(self):
        return _reference_id(self, "by")

    def get_action_label(self) -> str:
        return dict(PAY_LOG_ACTIONS).get(self.action, self.action or "-")


class Installment(me.EmbeddedDocument):
    """งวดของรายการย่อย เก็บวันครบกำหนด, จำนวนเงินของงวด และสถานะการจ่าย
    (ส่วนการจ่ายบันทึกด้วยปุ่ม "จ่ายแล้ว" ที่หน้ารายละเอียด)"""

    _id = me.ObjectIdField(required=True, default=ObjectId)
    due_date = me.DateTimeField()
    amount = me.DecimalField(
        min_value=0,
        max_value=1e12,
        precision=2,
        rounding=decimal.ROUND_HALF_EVEN,
    )
    paid_date = me.DateTimeField()
    paid_by = me.ReferenceField("User", dbref=True)  # ผู้บันทึกการจ่าย
    payment_number = me.StringField(max_length=128)  # เลขที่เอกสาร / ใบจ่ายเงิน
    paid_amount = me.DecimalField(
        min_value=0,
        max_value=1e12,
        precision=2,
        rounding=decimal.ROUND_HALF_EVEN,
    )
    # ประวัติการกดจ่าย / ยกเลิกจ่าย (เก่าสุดก่อน)
    pay_log = me.EmbeddedDocumentListField(PayLogEntry)

    def is_paid(self) -> bool:
        return self.paid_date is not None

    def get_status(self, today: datetime.date | None = None) -> str:
        """paid / overdue (เลยวันครบกำหนด) / upcoming (เหลือ 0–30 วัน) / unpaid"""
        return installment_status(self.due_date, self.paid_date, today)


class ItemDetail(me.EmbeddedDocument):
    """แถวย่อยของรายการย่อย: ยี่ห้อ / รุ่น / S/N / รหัสครุภัณฑ์ / รายละเอียด เพิ่มได้หลายแถว"""

    brand = me.StringField(max_length=100)
    model_name = me.StringField(max_length=100)
    serial_number = me.StringField(max_length=100)
    asset_code = me.StringField(max_length=100)
    details = me.StringField()

    def get_serial_number(self) -> str:
        if self.serial_number:
            return self.serial_number
        if self.details:
            match = re.search(r"(?:S/N|SN|Serial(?:\s*Number)?)\s*[:=]\s*([^\n\r]+)", self.details, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    def get_asset_code(self) -> str:
        if self.asset_code:
            return self.asset_code
        if self.details:
            match = re.search(r"(?:รหัสครุภัณฑ์|Asset(?:\s*Code)?|ครุภัณฑ์)\s*[:=]\s*([^\n\r]+)", self.details, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    def get_other_details(self) -> str:
        """รายละเอียดอื่น ๆ ที่ไม่ใช่ S/N หรือรหัสครุภัณฑ์ (กรณีข้อมูลเก่าเก็บปนกันใน details)"""
        if self.serial_number or self.asset_code:
            return (self.details or "").strip()
        if not self.details:
            return ""
        lines = []
        for line in self.details.splitlines():
            line_s = line.strip()
            if not line_s:
                continue
            if re.match(r"^(?:S/N|SN|Serial(?:\s*Number)?)\s*[:=]", line_s, re.IGNORECASE):
                continue
            if re.match(r"^(?:รหัสครุภัณฑ์|Asset(?:\s*Code)?|ครุภัณฑ์)\s*[:=]", line_s, re.IGNORECASE):
                continue
            lines.append(line_s)
        return "\n".join(lines)


class ProcurementItem(me.Document):
    """รายการย่อยของ MA (collection แยก) ทุก query ต้อง scope ด้วย organization"""

    meta = {
        "collection": "procurement_items",
        "strict": False,  # เอกสารเก่าที่ยังมี brand / model_name / details ระดับรายการต้องยังโหลดได้
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
    quantity = me.IntField(min_value=1, default=1)
    unit = me.StringField(max_length=50)
    account_code = me.StringField(max_length=200, choices=ALL_ACCOUNT_CODE_CHOICES)
    start_date = me.DateTimeField()
    end_date = me.DateTimeField()
    amount = me.DecimalField(
        required=True,
        min_value=0,
        max_value=1e12,
        precision=2,
        rounding=decimal.ROUND_HALF_EVEN,
    )
    # ยี่ห้อ / รุ่น / S/N / รหัสครุภัณฑ์ / รายละเอียด เป็นแถวย่อย เพิ่มได้ตามต้องการ
    sub_items = me.EmbeddedDocumentListField(ItemDetail)
    # เปิด/ปิด การระบุ S/N และ รหัสครุภัณฑ์ ในฟอร์ม
    has_sub_item_sn = me.BooleanField(default=None)
    has_sub_item_asset = me.BooleanField(default=None)

    # ช่องจากขั้นที่ 3 ของขอซื้อขอจ้างเดิม (#27) ผู้ชนะและราคาต่อหน่วยไม่บังคับ
    winner = me.StringField(max_length=200)
    unit_price = me.DecimalField(
        min_value=0,
        max_value=1e12,
        precision=2,
        rounding=decimal.ROUND_HALF_EVEN,
    )
    note = me.StringField()

    responsible_by = me.ListField(me.ReferenceField("OrganizationUserRole", dbref=True))
    # ฝ่ายที่มองเห็น / รับผิดชอบ: เลือกได้ในฟอร์ม หรือคำนวณจาก responsible_by หากไม่ได้กำหนดเอง
    responsible_divisions = me.ListField(me.ReferenceField("Division", dbref=True))
    has_custom_responsible_divisions = me.BooleanField(default=False)

    reminder_kind = me.StringField(choices=REMINDER_KIND_CHOICES, default="ma", required=True)
    requires_activation = me.BooleanField(default=False)

    # ตั้งค่าการเตือน (#28, #29) ดู kampan/utils/reminders.py
    expiry_reminder_offsets = me.ListField(
        me.StringField(choices=REMINDER_OFFSET_CHOICES), default=default_reminder_offsets
    )
    payment_reminder_offsets = me.ListField(
        me.StringField(choices=ALL_PAYMENT_OFFSET_CHOICES), default=default_payment_reminder_offsets
    )
    # จำนวนวันก่อน end_date ที่กรอกเอง (เตือนหมดอายุ)
    reminder_offsets_days = me.ListField(
        me.IntField(min_value=1, max_value=MAX_REMINDER_OFFSET_DAYS), default=list
    )
    # วันที่เตือนเจาะจง (เก็บ ค.ศ. เที่ยงคืน กรอกเป็น พ.ศ. ในฟอร์ม)
    custom_reminder_dates = me.ListField(me.DateTimeField(), default=list)

    # แบ่งจ่ายเป็นงวดไหม: False = จ่ายแล้วตอนสร้าง MA (ไม่เก็บงวด ไม่นับความคืบหน้า / การเตือนจ่าย / งวดค้าง)
    # None = เอกสารที่สร้างก่อนมี field นี้ ใช้จำนวนงวด (>1 = แบ่งงวด) ดู pays_in_installments
    # ข้อมูลเดิมที่ mode เป็น False แต่เก็บงวดเดียวไว้ ถือว่าไม่มีการจ่ายเช่นกัน (งวดนั้นถูกมองข้าม)
    installment_mode = me.BooleanField(default=None)
    installments = me.EmbeddedDocumentListField(Installment)

    # Audit fields
    created_by = me.ReferenceField("User", dbref=True)
    last_updated_by = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(required=True, default=datetime.datetime.now, auto_now=True)

    def __init__(self, *args, **values):
        super().__init__(*args, **values)
        if "responsible_divisions" in values and "_created" not in values and "__auto_convert" not in values:
            self.has_custom_responsible_divisions = True

    def clean(self):
        # เฉพาะรายการที่แบ่งจ่ายเป็นงวดต้องมีงวด รายการที่ไม่แบ่งงวดไม่มีการจ่าย (ไม่เก็บงวด)
        if self.installment_mode and not self.installments:
            raise me.ValidationError("รายการย่อยต้องมีอย่างน้อย 1 งวด")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise me.ValidationError("วันที่สิ้นสุดต้องมากกว่าหรือเท่ากับวันที่เริ่มต้น")

        organization_id = getattr(self.organization, "id", None)
        for member in self.responsible_by or []:
            if _reference_id(member, "organization") != organization_id:
                raise me.ValidationError("ผู้รับผิดชอบต้องเป็นสมาชิกของหน่วยงานเดียวกับ MA")

        if self.has_custom_responsible_divisions:
            for division in self.responsible_divisions or []:
                if _reference_id(division, "organization") != organization_id:
                    raise me.ValidationError("ฝ่ายต้องเป็นของหน่วยงานเดียวกับ MA")
        else:
            divisions = []
            for member in self.responsible_by or []:
                division = member.division
                if division and all(division.id != existing.id for existing in divisions):
                    divisions.append(division)
            self.responsible_divisions = divisions

    def get_category_label(self) -> str:
        return dict(ITEM_CATEGORY_CHOICES).get(self.category, self.category or "-")

    def get_reminder_kind_label(self) -> str:
        return dict(REMINDER_KIND_CHOICES).get(self.reminder_kind, self.reminder_kind or "-")

    def pays_in_installments(self) -> bool:
        """รายการนี้มีการจ่ายไหม (เฉพาะที่แบ่งจ่ายเป็นงวด) ไม่ใช่ = ไม่มีการจ่ายเลย"""
        if self.installment_mode is not None:
            return bool(self.installment_mode)
        return len(self._data.get("installments") or []) > 1

    def has_sn(self) -> bool:
        if self.has_sub_item_sn is not None:
            return bool(self.has_sub_item_sn)
        return any(bool(sub.serial_number) for sub in self.sub_items or [])

    def has_asset(self) -> bool:
        if self.has_sub_item_asset is not None:
            return bool(self.has_sub_item_asset)
        return any(bool(sub.asset_code) for sub in self.sub_items or [])

    def has_other_details(self) -> bool:
        return any(bool(sub.details and sub.details.strip()) for sub in self.sub_items or [])

    def get_sorted_installments(self) -> list[Installment]:
        """งวดเรียงตามวันครบกำหนด รายการที่ไม่มีการจ่ายไม่มีงวด (แม้ข้อมูลเดิมจะเก็บงวดไว้)"""
        if not self.pays_in_installments():
            return []
        return sorted(self.installments, key=lambda installment: installment.due_date or datetime.datetime.max)

    def get_installment(self, installment_id) -> Installment | None:
        if not self.pays_in_installments():
            return None
        for installment in self.installments:
            if str(installment._id) == str(installment_id):
                return installment
        return None

    def _installments_without_dereference(self) -> list[Installment]:
        """งวดจาก ``_data`` ตรง ๆ: อ่าน ``self.installments`` จะ dereference ``paid_by`` ของทุกงวด
        (1 query ต่อรายการย่อย) ซึ่งการคำนวณสถานะไม่ได้ใช้ รายการที่ไม่มีการจ่ายคืนค่าว่าง"""
        if not self.pays_in_installments():
            return []
        return list(self._data.get("installments") or [])

    def get_next_unpaid_installment(self) -> Installment | None:
        """งวดที่ยังไม่จ่ายซึ่งครบกำหนดเร็วที่สุด"""
        unpaid = [installment for installment in self._installments_without_dereference() if not installment.is_paid()]
        if not unpaid:
            return None
        return min(unpaid, key=lambda installment: installment.due_date or datetime.datetime.max)

    def get_paid_count(self) -> int:
        return sum(1 for installment in self._installments_without_dereference() if installment.is_paid())

    def get_installment_count(self) -> int:
        return len(self._installments_without_dereference())

    def get_payment_status(self, today: datetime.date | None = None) -> str:
        """สถานะของงวดที่ยังไม่จ่ายซึ่งครบกำหนดเร็วสุด (แย่สุดของรายการนี้) หรือ paid เมื่อจ่ายครบ
        รายการที่ไม่แบ่งจ่ายเป็นงวด = จ่ายแล้วตอนสร้าง MA (paid) ไม่มีงวดให้จ่ายหรือเตือน"""
        if not self.pays_in_installments():
            return "paid"
        return item_payment_status(
            ((installment.due_date, installment.paid_date) for installment in self._installments_without_dereference()),
            today,
        )

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
            ("organization", "parent_procurement"),
        ],
    }

    image = me.ImageField()
    # บังคับในฟอร์ม แต่ไม่บังคับใน model และซ้ำได้
    psu_disbursement_number = me.StringField(max_length=128)
    disbursement_date = me.DateTimeField()
    name = me.StringField(max_length=255, required=True)
    company = me.StringField(max_length=255, required=True)
    total_amount = me.DecimalField(
        required=True,
        min_value=0,
        max_value=1e12,
        precision=2,
        rounding=decimal.ROUND_HALF_EVEN,
    )
    # status: สถานะการต่ออายุ (renewal process) เริ่มที่ review
    status = me.StringField(choices=RENEWAL_STATUS_CHOICES, default="review")
    # ผู้รับผิดชอบขออะไรไว้ตอน status = renewal-requested (renew / stop)
    renewal_request = me.StringField(choices=RENEWAL_REQUEST_CHOICES)
    # สถานะการใช้งาน: คำนวณตอนบันทึกและ controller อัปเดตรายวัน (ค่าที่เก็บอาจค้างถ้า controller ไม่รัน)
    usage_status = me.StringField(choices=USAGE_STATUS_CHOICES)

    organization = me.ReferenceField("Organization", dbref=True, required=True)

    # เชื่อมโยงสัญญาหลัก / สัญญาย่อยที่ duplicate แยกออกมา
    parent_procurement = me.ReferenceField("Procurement", dbref=True)

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

    def get_renewal_status(self) -> str | None:
        """สถานะการต่ออายุที่ปรับค่าเดิม (active / pending) เป็น review แล้ว"""
        return normalize_renewal_status(self.status)

    def get_renewal_status_label(self) -> str:
        return dict(RENEWAL_STATUS_CHOICES).get(self.status, self.status or "-")

    def get_usage_status_label(self) -> str:
        return dict(USAGE_STATUS_CHOICES).get(self.usage_status, "-")

    def compute_usage_status(self, today: datetime.date | None = None) -> str | None:
        """สถานะการใช้งานจากรายการย่อย: วันเริ่มแรกสุดถึงวันสิ้นสุดสุดท้าย (แบบร่างไม่มี)"""
        if self.status == "draft":
            return None
        items = self.get_items()
        starts = [item.start_date for item in items if item.start_date]
        ends = [item.end_date for item in items if item.end_date]
        return compute_usage_status(min(starts) if starts else None, max(ends) if ends else None, today)

    def refresh_usage_status(self, today: datetime.date | None = None) -> bool:
        """คำนวณใหม่แล้วเขียนแบบ atomic ถ้าค่าเปลี่ยน (ไม่แตะ updated_date เพราะใช้กันฟอร์มแก้ไขชนกัน)"""
        value = self.compute_usage_status(today)
        updated = Procurement.objects(id=self.pk, organization=self.organization).filter(
            __raw__={"usage_status": {"$ne": value}}
        ).update_one(set__usage_status=value)
        self.usage_status = value
        return bool(updated)

    def is_renewed(self) -> bool:
        return self.status == "renewed" or _reference_id(self, "renewed_to") is not None

    def get_child_procurements(self) -> list["Procurement"]:
        cached = self.__dict__.get("_child_procurements_cache")
        if cached is not None:
            return cached
        if not self.pk:
            return []
        cached = list(Procurement.objects(parent_procurement=self, organization=self.organization).order_by("id"))
        self.__dict__["_child_procurements_cache"] = cached
        return cached

    def has_child_procurements(self) -> bool:
        cached = self.__dict__.get("_child_procurements_cache")
        if cached is not None:
            return len(cached) > 0
        if not self.pk:
            return False
        return len(self.get_child_procurements()) > 0

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
        paying = [item.get_payment_status(today) for item in self.get_items() if item.pays_in_installments()]
        if not paying and self.get_items():
            return "paid"  # ไม่มีรายการที่แบ่งจ่ายเป็นงวด = จ่ายแล้วทั้งหมดตอนสร้าง MA
        return worst_payment_status(paying)

    def get_unpaid_installments(self, single: bool = False) -> list:
        """งวดที่ยังไม่ได้บันทึกจ่ายของทุกรายการย่อย ``[(item, ลำดับงวด, installment)]`` เรียงตามวันครบกำหนด

        รายการย่อยที่ไม่ได้ติ๊ก "แบ่งจ่ายเป็นงวด" ไม่มีการจ่าย จึงไม่มีงวดให้นับ (``single=True`` จึงคืนค่าว่างเสมอ
        คงพารามิเตอร์ไว้ให้ ``pay_single_installments_on_renewal`` ซึ่งไม่ทำอะไรแล้ว)
        """
        rows = []
        if single:
            return rows
        for item in self.get_items():
            for index, installment in enumerate(item.get_sorted_installments(), start=1):
                if installment.due_date and not installment.is_paid():
                    rows.append((item, index, installment))
        return sorted(rows, key=lambda row: row[2].due_date)

    def pay_single_installments_on_renewal(self, user) -> int:
        """ไม่ทำอะไร (คืน 0): รายการที่ไม่แบ่งจ่ายเป็นงวดไม่มีการจ่าย จึงไม่มีงวดให้บันทึกจ่ายตอนต่ออายุ
        (เดิมบันทึกงวดเดียวว่าจ่ายแล้วตอนต่ออายุ) คงฟังก์ชันไว้ให้ผู้เรียกเดิม"""
        return 0

    def get_installment_progress(self) -> tuple[int, int]:
        """(จำนวนงวดที่จ่ายแล้ว, จำนวนงวดทั้งหมด) ของทุกรายการย่อย"""
        items = self.get_items()
        return (
            sum(item.get_paid_count() for item in items),
            sum(item.get_installment_count() for item in items),
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

    def _unique_references(self, field_name: str, lookup_key: str) -> list:
        """เอกสารใน ``field_name`` ของทุกรายการย่อย ไม่ซ้ำ ตามลำดับที่พบ

        ถ้า ``attach_items(..., with_responsibles=True)`` โหลดเอกสารไว้ให้แล้วใช้ของที่โหลดไว้ (ไม่ query ต่อแถว)
        """
        lookup = self.__dict__.get(lookup_key)
        documents = []
        seen = set()
        for item in self.get_items():
            if lookup is None:
                references = [(getattr(document, "id", None), document) for document in getattr(item, field_name) or []]
            else:
                references = [
                    (document_id, lookup.get(document_id)) for document_id in _reference_ids(item, field_name)
                ]
            for document_id, document in references:
                if document_id and document is not None and document_id not in seen:
                    seen.add(document_id)
                    documents.append(document)
        return documents

    def get_responsible_members(self) -> list:
        return self._unique_references("responsible_by", "_responsible_members_by_id")

    def get_responsible_divisions(self) -> list:
        return self._unique_references("responsible_divisions", "_responsible_divisions_by_id")

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
        - เอกสารที่มีอยู่แล้วเขียน / ลบเฉพาะเมื่อ ``updated_date`` ใน DB ยังเท่ากับตอนโหลด
          ถ้ามีคนแก้หรือบันทึกจ่ายงวดไปก่อน คืนส่วนที่เขียนไปแล้วแล้ว raise ConcurrentEditConflict
        """
        items = list(items)
        removed_items = [item for item in removed_items if item.pk]
        if not items:
            raise me.ValidationError("MA ต้องมีรายการย่อยอย่างน้อย 1 รายการ")

        if self.status != "draft":
            sum_error = check_item_sum(self.total_amount, (item.amount for item in items))
            if sum_error:
                raise me.ValidationError(sum_error)
        else:
            if self.total_amount is None:
                from kampan.utils.money import money_sum

                self.total_amount = money_sum(item.amount for item in items if item.amount)
            if not self.company:
                self.company = "-"

        # สถานะการใช้งานคำนวณใหม่ทุกครั้งที่บันทึก (controller อัปเดตรายวัน) แบบร่างไม่มี
        if self.status == "draft":
            self.usage_status = None
        else:
            starts = [item.start_date for item in items if item.start_date]
            ends = [item.end_date for item in items if item.end_date]
            self.usage_status = compute_usage_status(min(starts) if starts else None, max(ends) if ends else None)

        is_new = self.pk is None
        if is_new:
            # ตั้ง id ก่อน รายการย่อยจึง validate ReferenceField ได้ทั้งที่ยังไม่ได้เขียนหัว
            self.id = ObjectId()

        # เวลาแก้ไขตอนโหลด ใช้เป็นเงื่อนไขการเขียน (กันเขียนทับการแก้ / จ่ายงวดที่เกิดหลังโหลด)
        loaded_header_date = None if is_new else self.updated_date
        loaded_item_dates = {item.pk: item.updated_date for item in items + removed_items if item.pk}

        # auto_now ของ DateTimeField ไม่มีผลใน MongoEngine จึงตั้งเวลาแก้ไขเอง (ใช้ตรวจการแก้ไขชนกันด้วย)
        # ตัดเหลือมิลลิวินาทีให้ตรงกับที่ Mongo เก็บ จึงใช้เป็นเงื่อนไขตอนคืนข้อมูลได้
        now = datetime.datetime.now()
        now = now.replace(microsecond=now.microsecond // 1000 * 1000)
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
        written = {"header": False, "items": [], "deleted": []}
        try:
            if is_new:
                self.save(force_insert=True, validate=False)
            else:
                self.save(validate=False, save_condition={"updated_date": loaded_header_date})
            written["header"] = True
            for item in items:
                if item.pk in loaded_item_dates:
                    item.save(validate=False, save_condition={"updated_date": loaded_item_dates[item.pk]})
                else:
                    item.save(validate=False)
                written["items"].append(item)
            for item in removed_items:
                if not ProcurementItem.objects(id=item.pk, updated_date=loaded_item_dates[item.pk]).delete():
                    raise ConcurrentEditConflict()
                written["deleted"].append(item)
        except (me.errors.SaveConditionError, ConcurrentEditConflict) as error:
            logger.info("save_with_items conflict for procurement %s, restoring", self.pk)
            self._restore(snapshot, written, is_new, now)
            raise ConcurrentEditConflict() from error
        except Exception:
            logger.exception("save_with_items failed for procurement %s, restoring", self.pk)
            self._restore(snapshot, written, is_new, now)
            raise

        self.__dict__["_items_cache"] = items
        return self

    def _matching_children(self, item: ProcurementItem) -> list:
        """สัญญาย่อยที่เป็นสำเนาของรายการนี้ (parent คือ MA นี้ และมีรายการย่อยเดียวชื่อเดียวกัน)"""
        return [
            child
            for child in Procurement.objects(parent_procurement=self, organization=self.organization)
            if [child_item.name for child_item in child.get_items()] == [item.name]
        ]

    def get_item_delete_block(self, item: ProcurementItem) -> str | None:
        """เหตุผลที่ลบรายการย่อยนี้ไม่ได้ (ไม่มี = ลบได้)"""
        if len(self.get_items()) <= 1:
            return "MA ต้องมีรายการย่อยอย่างน้อย 1 รายการ"
        if any(installment.is_paid() for installment in item.installments or []):
            return "รายการนี้มีงวดที่จ่ายแล้ว ลบไม่ได้"
        # สัญญาย่อยที่เป็นสำเนาจะถูกลบไปด้วย ถ้าฝั่งสัญญาย่อยบันทึกจ่ายไปแล้วห้ามลบ (กันประวัติการจ่ายหาย)
        for child in self._matching_children(item):
            if any(
                installment.is_paid()
                for child_item in child.get_items()
                for installment in child_item.installments or []
            ):
                return "สัญญาย่อยของรายการนี้มีงวดที่จ่ายแล้ว ลบไม่ได้"
        return None

    def delete_item(self, item: ProcurementItem, user=None) -> None:
        """ลบรายการย่อยของ MA นี้ พร้อมประวัติแจ้งเตือนและสำเนาสัญญาย่อยของรายการนั้น แล้วตั้งยอดรวมหัวเป็นผลรวมที่เหลือ

        สัญญาย่อยที่ตรงกัน = Procurement ที่ parent_procurement คือ MA นี้ และมีรายการย่อยเดียวชื่อเดียวกับรายการที่ลบ
        raise ItemDeleteError เมื่อลบไม่ได้ และ ConcurrentEditConflict เมื่อมีคนแก้ MA ระหว่างนั้น
        """
        from kampan.utils.money import money_sum
        from .reminder_logs import ReminderLog

        items = self.get_items()
        if not any(existing.pk == item.pk for existing in items):
            raise ItemDeleteError("ไม่พบรายการย่อยใน MA นี้")
        block = self.get_item_delete_block(item)
        if block:
            raise ItemDeleteError(block)

        remaining = [existing for existing in items if existing.pk != item.pk]
        children = self._matching_children(item)

        self.total_amount = money_sum(existing.amount for existing in remaining if existing.amount)
        if user is not None:
            self.last_updated_by = user
        self.save_with_items(remaining, removed_items=[item])

        ReminderLog.objects(item=item.pk).delete()
        for child in children:
            child_item_ids = [child_item.pk for child_item in child.get_items()]
            ReminderLog.objects(item__in=child_item_ids).delete()
            ProcurementItem.objects(procurement=child, organization=self.organization).delete()
            try:
                if child.image:
                    child.image.delete()
            except Exception:
                logger.warning("deleting image of child procurement %s failed", child.pk)
            Procurement.objects(id=child.pk, organization=self.organization).delete()

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
            # คำขอที่ผู้รับผิดชอบขอ ณ ตอนโหลด ถ้าเปลี่ยนไประหว่างนั้น claim ไม่ได้
            renewal_request=self.renewal_request,
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

    def _restore(self, snapshot, written, is_new, now):
        """คืนเฉพาะเอกสารที่ save_with_items เขียน / ลบไปแล้ว

        เอกสารที่เขียนแล้วคืนเมื่อ ``updated_date`` ยังเป็นของรอบนี้ (``now``) เท่านั้น ไม่ทับการแก้ของคนอื่นที่ตามมา
        """
        items_collection = ProcurementItem._get_collection()
        try:
            if is_new:
                for item in written["items"]:
                    items_collection.delete_one({"_id": item.pk})
                self._get_collection().delete_one({"_id": self.pk})
                return

            snapshot_items = {raw["_id"]: raw for raw in snapshot["items"]}
            for item in written["items"]:
                raw = snapshot_items.get(item.pk)
                if raw is None:
                    items_collection.delete_one({"_id": item.pk})
                else:
                    items_collection.replace_one({"_id": item.pk, "updated_date": now}, raw)
            for item in written["deleted"]:
                raw = snapshot_items.get(item.pk)
                if raw is not None:
                    items_collection.replace_one({"_id": item.pk}, raw, upsert=True)
            if written["header"] and snapshot["procurement"]:
                self._get_collection().replace_one({"_id": self.pk, "updated_date": now}, snapshot["procurement"])
        except Exception:
            logger.exception("restore after failed save_with_items failed for procurement %s", self.pk)


def attach_items(
    procurements: Iterable[Procurement], organization, with_responsibles: bool = False
) -> list[Procurement]:
    """โหลดรายการย่อยของหลาย MA ด้วย query เดียว แล้ว cache ไว้ใน MA แต่ละตัว (กัน N+1 ในหน้ารายการ)

    ``with_responsibles``: โหลดผู้รับผิดชอบ (พร้อมผู้ใช้) และฝ่ายของทุก MA ด้วยอย่างละ 1 query
    ให้ ``get_responsible_members`` / ``get_responsible_divisions`` / ``display_user_fullname`` ไม่ query ต่อแถว
    """
    procurements = list(procurements)
    by_id = {procurement.pk: [] for procurement in procurements}
    if by_id:
        items = ProcurementItem.objects(organization=organization, procurement__in=list(by_id)).order_by("id")
        for item in items:
            procurement_id = _reference_id(item, "procurement")
            if procurement_id in by_id:
                by_id[procurement_id].append(item)

        # Batch-load child procurements for all rows (กัน N+1 ในหน้ารายการ)
        children_by_parent = {p.pk: [] for p in procurements}
        children = Procurement.objects(
            organization=organization, parent_procurement__in=list(by_id)
        ).only("id", "name", "total_amount", "parent_procurement")
        for child in children:
            parent_id = _reference_id(child, "parent_procurement")
            if parent_id in children_by_parent:
                children_by_parent[parent_id].append(child)
        for p in procurements:
            p.__dict__["_child_procurements_cache"] = children_by_parent[p.pk]

        # Batch-load parent procurements
        parent_ids = {_reference_id(p, "parent_procurement") for p in procurements} - {None}
        if parent_ids:
            parents = {
                parent.id: parent
                for parent in Procurement.objects(id__in=list(parent_ids), organization=organization).only(
                    "id", "name", "psu_disbursement_number"
                )
            }
            for p in procurements:
                parent_id = _reference_id(p, "parent_procurement")
                if parent_id in parents:
                    p._data["parent_procurement"] = parents[parent_id]
    for procurement in procurements:
        procurement.__dict__["_items_cache"] = by_id[procurement.pk]
    if with_responsibles:
        _attach_responsibles(procurements, organization)
    return procurements


def _attach_responsibles(procurements: list[Procurement], organization) -> None:
    items = [item for procurement in procurements for item in procurement.get_items()]
    member_ids = {member_id for item in items for member_id in _reference_ids(item, "responsible_by")}
    division_ids = {division_id for item in items for division_id in _reference_ids(item, "responsible_divisions")}
    paid_by_ids = {
        _reference_id(installment, "paid_by")
        for item in items
        for installment in (item._data.get("installments") or [])
    } - {None}

    members = (
        list(OrganizationUserRole.objects(id__in=list(member_ids), organization=organization)) if member_ids else []
    )
    user_ids = ({_reference_id(member, "user") for member in members} | paid_by_ids) - {None}
    users = {user.id: user for user in User.objects(id__in=list(user_ids))} if user_ids else {}
    for member in members:
        user = users.get(_reference_id(member, "user"))
        if user is not None:
            # ใส่ผู้ใช้ที่โหลดแล้วแทน DBRef ตรง ๆ ไม่ให้ member.user query ซ้ำ (ไม่ผ่าน setter จึงไม่ถูกนับว่าแก้ไข)
            member._data["user"] = user
    for item in items:
        for installment in (item._data.get("installments") or []):
            user = users.get(_reference_id(installment, "paid_by"))
            if user is not None:
                installment._data["paid_by"] = user
    members_by_id = {member.id: member for member in members}
    divisions_by_id = (
        {division.id: division for division in Division.objects(id__in=list(division_ids), organization=organization)}
        if division_ids
        else {}
    )
    for procurement in procurements:
        procurement.__dict__["_responsible_members_by_id"] = members_by_id
        procurement.__dict__["_responsible_divisions_by_id"] = divisions_by_id


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


def parent_procurement_ids(organization=None) -> list:
    """id ของสัญญาหลักที่มีสัญญาย่อยอ้างถึง (สัญญาหลักเป็นแค่ข้อมูลอ้างอิง งานเตือนและหน้ารายการใช้สัญญาย่อยแทน)"""
    children = Procurement.objects(parent_procurement__ne=None)
    if organization is not None:
        children = children.filter(organization=organization)
    ids = {_reference_id(child, "parent_procurement") for child in children.only("parent_procurement")}
    return list(ids - {None})


def payment_statuses(procurement_ids: Iterable, organization, today: datetime.date | None = None) -> dict:
    """สถานะการจ่ายของหลาย MA ``{procurement_id: status}`` ด้วย query เดียว ไม่ขึ้นกับจำนวน MA

    อ่านเฉพาะวันครบกำหนด / วันจ่ายของงวดแบบดิบ (ไม่สร้างเอกสารและไม่ dereference ผู้บันทึกการจ่าย)
    MA ที่ไม่มีรายการย่อยเป็น unpaid เหมือน ``Procurement.get_payment_status``
    """
    item_statuses = {procurement_id: [] for procurement_id in procurement_ids}
    if not item_statuses:
        return {}
    rows = (
        ProcurementItem.objects(organization=organization, procurement__in=list(item_statuses))
        .only("procurement", "installments", "installment_mode")
        .as_pymongo()
    )
    for row in rows:
        procurement_id = getattr(row["procurement"], "id", row["procurement"])
        installments = row.get("installments") or []
        mode = row.get("installment_mode")
        # รายการที่ไม่แบ่งจ่ายเป็นงวดจ่ายแล้วตอนสร้าง MA (mode ไม่ระบุ = ข้อมูลเดิม ใช้จำนวนงวด > 1)
        if not (mode if mode is not None else len(installments) > 1):
            item_statuses[procurement_id].append("paid")
            continue
        item_statuses[procurement_id].append(
            item_payment_status(
                ((installment.get("due_date"), installment.get("paid_date")) for installment in installments), today
            )
        )
    return {procurement_id: worst_payment_status(statuses) for procurement_id, statuses in item_statuses.items()}


class ItemDateOrderedIds:
    """id ของ MA เรียงตามวันที่ของรายการย่อย ให้ Mongo เรียง + skip + limit ทีละหน้า

    ใช้กับ ``ClampedPagination`` (รองรับ ``len()`` และ ``[start:stop]``) จึงไม่โหลดวันที่ของทุก MA เข้า Python
    มีแค่ id ของ MA ที่ผ่านตัวกรอง (ObjectId) ที่โหลดมาครั้งเดียวไว้ใช้เป็นเงื่อนไข $match และนับจำนวน
    MA ที่ไม่มีวันที่นั้น (เช่น ไม่มีรายการย่อย หรือจ่ายครบทุกงวดแล้ว) ต่อท้ายสุดตามลำดับเดิมของ queryset

    ``stages``: ขั้น aggregation ที่คำนวณ ``{"_id": "$procurement", "date": ...}`` ต่อหนึ่ง MA
    """

    # วันสิ้นสุดของรายการย่อยที่หมดอายุก่อน
    END_DATE = [{"$group": {"_id": "$procurement", "date": {"$min": "$end_date"}}}]
    # วันครบกำหนดของงวดที่ยังไม่จ่ายและใกล้ที่สุด
    NEXT_DUE_DATE = [
        # เฉพาะรายการที่แบ่งจ่ายเป็นงวด (ข้อมูลเดิมที่ mode ไม่ระบุแต่งวดเดียว และ mode = False ไม่มีการจ่าย)
        {
            "$match": {
                "$or": [
                    {"installment_mode": True},
                    {"installment_mode": None, "installments.1": {"$exists": True}},
                ]
            }
        },
        {"$unwind": "$installments"},
        {"$match": {"installments.paid_date": None, "installments.due_date": {"$ne": None}}},
        {"$group": {"_id": "$procurement", "date": {"$min": "$installments.due_date"}}},
    ]

    def __init__(self, procurement_queryset, organization, stages, reverse: bool = False):
        self.organization = organization
        self.stages = stages
        self.reverse = reverse
        self.ids = list(procurement_queryset.scalar("id"))
        self._with_date = None

    def __len__(self) -> int:
        return len(self.ids)

    def _items(self):
        return ProcurementItem.objects(organization=self.organization, procurement__in=self.ids)

    def _count_with_date(self) -> int:
        if self._with_date is None:
            rows = list(self._items().aggregate([*self.stages, {"$count": "n"}]))
            self._with_date = rows[0]["n"] if rows else 0
        return self._with_date

    def __getitem__(self, key):
        if not isinstance(key, slice):
            raise TypeError("ItemDateOrderedIds supports slicing only")
        start = key.start or 0
        stop = min(key.stop if key.stop is not None else len(self.ids), len(self.ids))
        if not self.ids or stop <= start:
            return []
        direction = -1 if self.reverse else 1
        pipeline = [
            *self.stages,
            {"$sort": {"date": direction, "_id": 1}},
            {"$skip": start},
            {"$limit": stop - start},
        ]
        page = [getattr(row["_id"], "id", row["_id"]) for row in self._items().aggregate(pipeline)]
        missing = stop - start - len(page)
        if missing > 0 and stop > self._count_with_date():
            # MA ที่ไม่มีวันที่นั้น ต่อท้ายสุดตามลำดับเดิม (เช่น จ่ายครบทุกงวดแล้ว)
            dated = {getattr(row["_id"], "id", row["_id"]) for row in self._items().aggregate(self.stages)}
            tail = [procurement_id for procurement_id in self.ids if procurement_id not in dated]
            offset = max(start - self._count_with_date(), 0)
            page += tail[offset : offset + missing]
        return page


def procurements_in_order(procurement_ids: list, organization) -> list[Procurement]:
    """MA ตาม id ที่ให้ (scope ด้วยหน่วยงาน) เรียงตามลำดับของ ``procurement_ids``"""
    by_id = {
        procurement.pk: procurement
        for procurement in Procurement.objects(id__in=list(procurement_ids), organization=organization)
    }
    return [by_id[procurement_id] for procurement_id in procurement_ids if procurement_id in by_id]
