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
    ("car_application", "ขอยืมรถยนตร์"),
]


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
