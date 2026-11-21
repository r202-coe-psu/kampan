import mongoengine as me
import bson
import datetime

from jinja2 import Environment, PackageLoader, select_autoescape, Template

import io
import base64
import markdown

EMAIL_TYPE = [
    ("to endorser", "ส่งถึงผู้มีสิทธิ์อนุญาตในแผนก"),
    ("to supervisor supplier", "ส่งถึงหัวหน้าแผนกพัสดุ"),
    ("to admin", "ส่งถึงเจ้าหน้าที่พัสดุ"),
    ("to staff", "ส่งถึงพนักงาน"),
    ("lost_break", "แจ้งเตือนวัสดุชำรุด/สูญหาย/แก้ไข"),
    ("car_application", "ขอยืมรถยนต์"),
    ("car_application_result", "แจ้งผลการขอใช้รถยนต์ถึงผู้ขอ"),
    ("car_reservation_submitted", "จองรถ: ยื่นใบขอใช้รถ"),
    ("car_reservation_approved", "จองรถ: อนุมัติขั้นหนึ่ง รอขั้นถัดไป"),
    ("car_reservation_active", "จองรถ: อนุมัติครบทุกขั้น"),
    ("car_reservation_denied", "จองรถ: ไม่อนุมัติใบขอใช้รถ"),
    ("car_reservation_cancel_requested", "จองรถ: ขอยกเลิกใบขอใช้รถ"),
    ("car_reservation_cancelled", "จองรถ: ยกเลิกใบขอใช้รถ"),
    ("car_reservation_completed", "จองรถ: ปิดงาน ขอให้ประเมินความพึงพอใจ"),
    ("car_reservation_close_disputed", "จองรถ: ผู้ขอแจ้งเวลาปิดงานไม่ถูกต้อง"),
    ("ma_assigned", "MA: แจ้งมอบหมายผู้รับผิดชอบ"),
    ("ma_expiry", "MA: เตือนใกล้หมดอายุ / สิ้นสุดสัญญา"),
    ("ma_payment", "MA: เตือนครบกำหนดจ่ายงวด"),
]

EMAIL_SYSTEMS = [
    ("inventory", "ระบบพัสดุ"),
    ("vehicle_lending", "ระบบยืมรถ"),
    ("car_reservation", "ระบบจองรถ"),
    ("procurement", "ระบบ MA"),
]

# ระบบของอีเมล -> module ของ org (Organization.has_module) org เห็นเฉพาะระบบที่เปิดใช้
EMAIL_SYSTEM_ORG_MODULE = {
    "inventory": "inventory",
    "vehicle_lending": "car",
    "car_reservation": "car_reservation",
    "procurement": "procurement",
}


def get_email_systems(
    organization: "Organization | None" = None, keep: str | None = None
) -> list[tuple[str, str]]:
    """keep: ระบบที่ต้องอยู่ในรายการเสมอ เช่นระบบของ template ที่กำลังแก้ แม้ org ปิด module ไปแล้ว"""
    if organization is None:
        return list(EMAIL_SYSTEMS)
    return [
        (system, label)
        for system, label in EMAIL_SYSTEMS
        if system == keep or organization.has_module(EMAIL_SYSTEM_ORG_MODULE[system])
    ]


# ระบบ -> class สีประจำ module ใน setup.css (.module-<name>)
EMAIL_SYSTEM_MODULE = {
    "inventory": "module-inventory",
    "vehicle_lending": "module-car",
    "car_reservation": "module-car",
    "procurement": "module-procurement",
}

# ข้อมูลประกอบของแต่ละประเภทอีเมล เก็บในโค้ด ไม่ได้เก็บใน DB (ไม่ต้อง migrate)
EMAIL_TYPE_INFO = {
    "to endorser": {
        "system": "inventory",
        "recipient": "ผู้มีสิทธิ์อนุญาตในแผนกของผู้เบิก",
        "trigger": "เมื่อพนักงานส่งคำขอเบิกวัสดุ",
    },
    "to supervisor supplier": {
        "system": "inventory",
        "recipient": "หัวหน้าแผนกพัสดุ",
        "trigger": "เมื่อผู้มีสิทธิ์อนุญาตในแผนกอนุมัติคำขอเบิก",
    },
    "to admin": {
        "system": "inventory",
        "recipient": "เจ้าหน้าที่พัสดุ",
        "trigger": "เมื่อหัวหน้าแผนกพัสดุอนุมัติคำขอเบิก",
    },
    "to staff": {
        "system": "inventory",
        "recipient": "ผู้ขอเบิก",
        "trigger": "เมื่อเจ้าหน้าที่พัสดุอนุมัติและนัดรับพัสดุ",
    },
    "lost_break": {
        "system": "inventory",
        "recipient": "หัวหน้าแผนกพัสดุ",
        "trigger": "เมื่อมีการแจ้งหรือแก้ไขรายการวัสดุชำรุด/สูญหาย",
    },
    "car_application": {
        "system": "vehicle_lending",
        "recipient": "ผู้อนุมัติขั้นถัดไป (หัวหน้าแผนก / ผู้อำนวยการ / ผู้ดูแล)",
        "trigger": "เมื่อมีคำขอใช้รถรออนุมัติในแต่ละขั้น",
    },
    "car_application_result": {
        "system": "vehicle_lending",
        "recipient": "ผู้ขอใช้รถ",
        "trigger": "เมื่อสถานะคำขอใช้รถเปลี่ยน (อนุมัติ / ปฏิเสธ)",
    },
    "car_reservation_submitted": {
        "system": "car_reservation",
        "recipient": "หัวหน้าฝ่ายของผู้ขอ",
        "trigger": "เมื่อผู้ขอยื่นใบขอใช้รถ",
    },
    "car_reservation_approved": {
        "system": "car_reservation",
        "recipient": "ผู้ดำรงตำแหน่งและผู้รับมอบหมายของขั้นอนุมัติถัดไป",
        "trigger": "เมื่อผู้อนุมัติขั้นก่อนหน้าอนุมัติ และยังมีขั้นถัดไป",
    },
    "car_reservation_active": {
        "system": "car_reservation",
        "recipient": "ผู้ขอและพนักงานขับรถ",
        "trigger": "เมื่อผู้อนุมัติขั้นสุดท้ายอนุมัติ ใบขอพร้อมใช้งาน",
    },
    "car_reservation_denied": {
        "system": "car_reservation",
        "recipient": "ผู้ขอใช้รถ",
        "trigger": "เมื่อผู้อนุมัติขั้นใดขั้นหนึ่งไม่อนุมัติ",
    },
    "car_reservation_cancel_requested": {
        "system": "car_reservation",
        "recipient": "ผู้ดำรงตำแหน่งและผู้รับมอบหมายของงานจัดรถ (dispatcher)",
        "trigger": "เมื่อผู้ขอแจ้งยกเลิกใบขอที่จัดรถแล้ว",
    },
    "car_reservation_cancelled": {
        "system": "car_reservation",
        "recipient": "ผู้ขอและพนักงานขับรถ",
        "trigger": "เมื่อยกเลิกใบขอใช้รถ (หรืองานจัดรถรับทราบการยกเลิก)",
    },
    "car_reservation_completed": {
        "system": "car_reservation",
        "recipient": "ผู้ขอใช้รถ",
        "trigger": "เมื่อพนักงานขับรถปิดงาน พร้อมลิงก์แบบประเมินความพึงพอใจ",
    },
    "car_reservation_close_disputed": {
        "system": "car_reservation",
        "recipient": "ผู้ดำรงตำแหน่งและผู้รับมอบหมายของงานจัดรถ (dispatcher)",
        "trigger": "เมื่อผู้ขอแจ้งว่าเวลาปิดงานที่พนักงานขับรถบันทึกไม่ถูกต้อง",
    },
    "ma_assigned": {
        "system": "procurement",
        "recipient": "ผู้รับผิดชอบรายการย่อยที่ถูกเพิ่มใหม่",
        "trigger": "เมื่อบันทึก MA หรือเพิ่มผู้รับผิดชอบในรายการย่อย (1 ฉบับต่อคนต่อรายการ)",
    },
    "ma_expiry": {
        "system": "procurement",
        "recipient": "ผู้รับผิดชอบรายการย่อย",
        "trigger": "ก่อนวันสิ้นสุดตามช่วงที่ติ๊ก, วันสิ้นสุด, วันที่ activate และวันที่เตือนเจาะจง",
    },
    "ma_payment": {
        "system": "procurement",
        "recipient": "ผู้รับผิดชอบรายการย่อย",
        "trigger": "วันครบกำหนดจ่ายแต่ละงวด และ 7 / 5 / 3 วันก่อนที่ติ๊กไว้",
    },
}


def get_email_types_by_system(
    organization: "Organization | None" = None, keep: str | None = None
) -> list[tuple[str, str, list[tuple[str, str]]]]:
    """[(system, system_label, [(type, type_label), ...]), ...] สำหรับ optgroup และ filter"""
    return [
        (
            system,
            system_label,
            [
                (value, label)
                for value, label in EMAIL_TYPE
                if EMAIL_TYPE_INFO[value]["system"] == system
            ],
        )
        for system, system_label in get_email_systems(organization, keep=keep)
    ]

# ตัวแปรที่ใช้ใน {{ ... }} ของหัวข้อและเนื้อหาได้ แยกตามประเภทอีเมล
# ต้องตรงกับ dict ที่ kampan/utils/email_utils.py ส่งให้ template.render() (มี test คุมไว้)
_ORDER_VARIABLES = [
    ("organization_name", "ชื่อองค์กร"),
    ("division_name", "ชื่อแผนกของผู้เบิก"),
    ("division_description", "รายละเอียดแผนก"),
    ("order_creator", "ชื่อผู้เบิก"),
    ("order_creator_email", "อีเมลผู้เบิก"),
    ("order_email", "อีเมลผู้เบิก (ชื่อเดิม)"),
    ("order_date", "วันเวลาที่ขอเบิก"),
    ("order_objective", "วัตถุประสงค์การเบิก"),
    ("sent_item_datetime", "วันเวลานัดรับพัสดุ"),
    ("sender_name", "ชื่อผู้ส่งอีเมล (ผู้กดดำเนินการ)"),
    ("sender_email", "อีเมลผู้ส่ง"),
    ("endorser_name", "ชื่อผู้รับอีเมล"),
    ("endorsement_url", "ลิงก์ไปหน้าอนุมัติ"),
]

# อีเมล MA ใช้เฉพาะ template ขององค์กร (kampan/utils/ma_email_templates.py) ตัวแปรต้องตรงกับ context ที่ ma_send_emails ส่งให้
_MA_COMMON_VARIABLES = [
    ("organization_name", "ชื่อองค์กร"),
    ("ma_name", "ชื่อสัญญา MA"),
    ("psu_number", "เลขที่ ม.อ.เบิกจ่ายของสัญญา (เป็น - ถ้าไม่มี)"),
    ("company", "บริษัท / ร้านค้า"),
    ("item_name", "ชื่อรายการย่อย"),
    ("noun", "คำเรียกรายการ เช่น MA / License / สัญญาเช่า-จ้างเหมา"),
    ("start_date", "วันเริ่มสัญญา"),
    ("end_date", "วันสิ้นสุดสัญญา"),
    ("detail_url", "ลิงก์ไปหน้ารายละเอียด MA"),
]
_MA_REMINDER_VARIABLES = _MA_COMMON_VARIABLES + [
    ("reminder_title", "หัวข้อการเตือน เช่น หมดอายุใน 30 วัน"),
    ("reminder_message", "ข้อความอธิบายการเตือน (หลายบรรทัด)"),
    ("target_date", "วันครบกำหนดที่เตือน (วันสิ้นสุด หรือวันครบกำหนดจ่ายงวด)"),
    ("days_text", "จำนวนวันที่เหลือ เช่น (อีก 7 วัน) / (วันนี้) / (เลยมาแล้ว 3 วัน)"),
]

EMAIL_TEMPLATE_VARIABLES = {
    "to endorser": _ORDER_VARIABLES,
    "to supervisor supplier": _ORDER_VARIABLES,
    "to admin": _ORDER_VARIABLES,
    "to staff": [
        (name, label) for name, label in _ORDER_VARIABLES if name != "endorsement_url"
    ],
    "lost_break": [
        ("organization_name", "ชื่อองค์กร"),
        ("lost_break_item_name", "ชื่อวัสดุ"),
        ("lost_break_item_quantity", "จำนวน"),
        ("lost_break_item_objective", "รายละเอียด/สาเหตุ"),
        ("lost_break_item_date", "วันเวลาที่แจ้ง"),
        ("lost_break_item_creator", "ชื่อผู้แจ้ง"),
        ("lost_break_item_email", "อีเมลผู้แจ้ง"),
        ("sender_name", "ชื่อผู้ส่งอีเมล"),
        ("sender_email", "อีเมลผู้ส่ง"),
        ("supervisor_supplier_name", "ชื่อหัวหน้าแผนกพัสดุ (ผู้รับอีเมล)"),
        ("endorser_name", "ชื่อผู้รับอีเมล"),
        ("endorsement_url", "ลิงก์ไปหน้าอนุมัติ"),
    ],
    "car_application": [
        ("organization_name", "ชื่อองค์กร"),
        ("division_name", "ชื่อแผนกของผู้ขอ"),
        ("order_name", "ชื่อผู้ขอยืมรถ"),
        ("order_email", "อีเมลผู้ขอยืมรถ"),
        ("departure_datetime", "วันเวลาออกเดินทาง"),
        ("car_application_objective", "เหตุผลการขอใช้รถ"),
        ("car", "ทะเบียนรถ"),
        ("sender_name", "ชื่อผู้ส่งอีเมล"),
        ("sender_email", "อีเมลผู้ส่ง"),
        ("endorser_name", "ชื่อผู้รับอีเมล"),
        ("endorsement_url", "ลิงก์ไปหน้าอนุมัติ"),
    ],
    "car_application_result": [
        ("organization_name", "ชื่อองค์กร"),
        ("division_name", "ชื่อแผนกของผู้ขอ"),
        ("order_name", "ชื่อผู้ขอยืมรถ (ผู้รับอีเมล)"),
        ("order_email", "อีเมลผู้ขอยืมรถ"),
        ("status_label", "สถานะล่าสุด เช่น รอพัสดุอนุมัติ / อนุมัติสำเร็จ / ปฏิเสธ"),
        ("denied_reason", "เหตุผลที่ไม่อนุมัติ (เป็น - ถ้าไม่ได้ปฏิเสธ)"),
        ("departure_datetime", "วันเวลาออกเดินทาง"),
        ("return_datetime", "วันเวลากลับ"),
        ("location", "สถานที่ไป"),
        ("car_application_objective", "เหตุผลการขอใช้รถ"),
        ("car", "ทะเบียนรถ"),
        ("driver_name", "ชื่อพนักงานขับรถ"),
        ("sender_name", "ชื่อผู้พิจารณา"),
        ("sender_email", "อีเมลผู้พิจารณา"),
        ("application_url", "ลิงก์ไปหน้ารายการขอใช้รถของผู้ขอ"),
    ],
    "ma_assigned": _MA_COMMON_VARIABLES + [("assigner_name", "ชื่อผู้มอบหมาย")],
    "ma_expiry": _MA_REMINDER_VARIABLES,
    "ma_payment": _MA_REMINDER_VARIABLES
    + [
        ("installment_index", "งวดที่ (ตัวเลข เป็นค่าว่างถ้าไม่ทราบ)"),
        ("due_date", "วันครบกำหนดจ่ายของงวด"),
    ],
}

# อีเมลของระบบจองรถทุกประเภทใช้ตัวแปรชุดเดียวกัน
# ต้องตรงกับ dict ที่ kampan/utils/car_reservation_email.py ส่งให้ template.render() (มี test คุมไว้)
_CAR_RESERVATION_VARIABLES = [
    ("organization_name", "ชื่อองค์กร"),
    ("requester_name", "ชื่อผู้ขอใช้รถ"),
    ("contact_name", "ชื่อผู้ติดต่อรับแจ้งสถานะ"),
    ("request_type_label", "ประเภทใบขอ"),
    ("destination", "สถานที่ปลายทาง"),
    ("departure", "วันเวลาออกเดินทาง"),
    ("return_at", "วันเวลากลับ"),
    ("status_label", "สถานะใบขอ"),
    ("step_label", "ขั้นอนุมัติที่รอพิจารณา (เป็น - ถ้าไม่มี)"),
    ("car_plate", "ทะเบียนรถ (ว่างถ้ายังไม่จัดรถ)"),
    ("driver_name", "ชื่อพนักงานขับรถ (ว่างถ้ายังไม่จัดรถ)"),
    ("reason", "เหตุผลการขอใช้รถ"),
    ("comment", "ความเห็นล่าสุดของผู้พิจารณา เช่น เหตุผลที่ไม่อนุมัติ/ยกเลิก (เป็น - ถ้าไม่มี)"),
    ("request_url", "ลิงก์ไปหน้ารายละเอียดใบขอ"),
    ("feedback_url", "ลิงก์ไปหน้าแบบประเมินความพึงพอใจของรถคันที่ใช้ (เลือกเที่ยวนี้ให้ ว่างถ้ายังไม่จัดรถ)"),
]

EMAIL_TEMPLATE_VARIABLES.update(
    {
        email_type: _CAR_RESERVATION_VARIABLES
        for email_type, info in EMAIL_TYPE_INFO.items()
        if info["system"] == "car_reservation"
    }
)


class EmailTemplate(me.Document):
    meta = {"collection": "email_templates"}

    name = me.StringField(require=True, max_length=255)
    subject = me.StringField(required=True, max_length=255)
    body = me.StringField(required=True)

    type = me.StringField(required=True, choices=EMAIL_TYPE, default=EMAIL_TYPE[0][0])

    organization = me.ReferenceField("Organization", required=True, dbref=True)
    is_default = me.BooleanField(
        require=True,
        default=False,
        false_values=(
            "False",
            "false",
        ),
        true_values=(
            "True",
            "true",
        ),
    )
    created_by = me.ReferenceField("User", dbref=True)
    last_updated_by = me.ReferenceField("User", dbref=True)

    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )

    def get_system(self):
        return EMAIL_TYPE_INFO.get(self.type, {}).get("system")

    def get_system_display(self):
        return dict(EMAIL_SYSTEMS).get(self.get_system(), "-")

    def get_system_module_class(self):
        return EMAIL_SYSTEM_MODULE.get(self.get_system(), "")

    def get_subject(self):
        return markdown.markdown(self.subject)

    def get_body(self):
        return markdown.markdown(self.body)
