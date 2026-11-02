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
]

EMAIL_SYSTEMS = [
    ("inventory", "ระบบพัสดุ"),
    ("vehicle_lending", "ระบบยืมรถ"),
]

# ระบบ -> class สีประจำ module ใน setup.css (.module-<name>)
EMAIL_SYSTEM_MODULE = {
    "inventory": "module-inventory",
    "vehicle_lending": "module-car",
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
}


def get_email_types_by_system():
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
        for system, system_label in EMAIL_SYSTEMS
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
}


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
