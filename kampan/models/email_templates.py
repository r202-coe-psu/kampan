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

    def get_subject(self):
        return markdown.markdown(self.subject)

    def get_body(self):
        return markdown.markdown(self.body)
