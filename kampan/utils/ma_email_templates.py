"""อีเมล MA ใช้ template ขององค์กรเท่านั้น (หน้า /email_templates ชนิด ma_assigned / ma_expiry / ma_payment)

- ไม่มีข้อความตายตัวในโค้ดตอนส่ง: ถ้าองค์กรยังไม่มี template ชนิดนั้นเลย ระบบสร้าง template เริ่มต้นเข้า collection เดียวกัน
  (แก้ / เปลี่ยนได้ที่หน้า template) ถ้ามี template ของชนิดนั้นแล้วแต่ไม่มีตัวที่เป็นค่าเริ่มต้น ไม่ส่งและบันทึกสาเหตุใน ReminderLog
- render ด้วย Jinja sandbox (ผู้ดูแลองค์กรแก้ template ได้ จึงห้ามรันนิพจน์ที่เข้าถึง object ภายในของระบบ)
"""

import logging

from jinja2 import TemplateError
from jinja2.sandbox import SandboxedEnvironment

from kampan import models

logger = logging.getLogger(__name__)

# reminder kind -> ชนิด template (expiry / activation / custom ใช้ชนิดเดียวกัน)
KIND_TO_TYPE = {
    "assigned": "ma_assigned",
    "payment": "ma_payment",
    "expiry": "ma_expiry",
    "activation": "ma_expiry",
    "custom": "ma_expiry",
}

NO_TEMPLATE_ERROR = "องค์กรยังไม่ได้ตั้งรูปแบบอีเมลเริ่มต้นของชนิดนี้"
BAD_TEMPLATE_ERROR = "รูปแบบอีเมลของชนิดนี้ไม่ถูกต้อง"

_FOOTER = """
ดูรายละเอียด: {{ detail_url }}

ด้วยความเคารพ
งานพัสดุ
อีเมลติดต่อ patsadu_diis@psu.ac.th
"""

_DETAIL_HEAD = """สัญญา MA: {{ ma_name }} (เลขที่ ม.อ.เบิกจ่าย {{ psu_number }})
บริษัท: {{ company }}
ช่วงสัญญา: {{ start_date }} – {{ end_date }}
"""

DEFAULT_TEMPLATES = {
    "ma_assigned": {
        "name": "MA: แจ้งมอบหมายผู้รับผิดชอบ (เริ่มต้น)",
        "subject": "[มอบหมาย] คุณได้รับมอบหมายให้เป็นผู้รับผิดชอบ {{ item_name }} (ม.อ.เบิกจ่าย {{ psu_number }})",
        "body": (
            "เรียน ผู้รับผิดชอบ\n\n"
            "{{ assigner_name }} ได้มอบหมายให้คุณเป็นผู้รับผิดชอบรายการต่อไปนี้\n\n"
            "สัญญา MA: {{ ma_name }} (เลขที่ ม.อ.เบิกจ่าย {{ psu_number }})\n"
            "รายการ: {{ item_name }}\n"
            "บริษัท: {{ company }}\n"
            "ช่วงสัญญา: {{ start_date }} – {{ end_date }}\n\n"
            "ระบบจะแจ้งเตือนก่อนหมดอายุและก่อนครบกำหนดจ่ายแต่ละงวด และเมื่อใกล้หมดอายุ "
            "กรุณากด \"ขอต่ออายุ\" หรือ \"ไม่ต่ออายุ\" ที่หน้ารายละเอียด\n" + _FOOTER
        ),
    },
    "ma_expiry": {
        "name": "MA: เตือนใกล้หมดอายุ / สิ้นสุดสัญญา (เริ่มต้น)",
        "subject": "[แจ้งเตือน] {{ reminder_title }} {{ item_name }} (ม.อ.เบิกจ่าย {{ psu_number }})",
        "body": (
            "เรียน ผู้รับผิดชอบ\n\n{{ noun }}: {{ item_name }}\n" + _DETAIL_HEAD + "\n{{ reminder_message }}\n" + _FOOTER
        ),
    },
    "ma_payment": {
        "name": "MA: เตือนครบกำหนดจ่ายงวด (เริ่มต้น)",
        "subject": "[แจ้งเตือน] {{ reminder_title }} {{ item_name }} (ม.อ.เบิกจ่าย {{ psu_number }})",
        "body": (
            "เรียน ผู้รับผิดชอบ\n\n{{ noun }}: {{ item_name }}\n" + _DETAIL_HEAD + "\n{{ reminder_message }}\n" + _FOOTER
        ),
    },
}


class MaEmailTemplateError(Exception):
    """ส่งอีเมลไม่ได้เพราะ template ขององค์กร ``str(error)`` เป็นข้อความที่แสดงใน ReminderLog ได้"""


_env = SandboxedEnvironment(autoescape=False, keep_trailing_newline=True)


def email_type_for(kind: str) -> str:
    return KIND_TO_TYPE.get(kind, "ma_expiry")


def get_template(organization, email_type: str):
    """template เริ่มต้นของชนิดนี้ในองค์กร · ไม่มีชนิดนี้เลย = สร้างตัวเริ่มต้นให้ · มีแต่ไม่มีตัวเริ่มต้น = MaEmailTemplateError"""
    template = models.EmailTemplate.objects(organization=organization, type=email_type, is_default=True).first()
    if template:
        return template
    if models.EmailTemplate.objects(organization=organization, type=email_type).count():
        raise MaEmailTemplateError(NO_TEMPLATE_ERROR)
    default = DEFAULT_TEMPLATES[email_type]
    return models.EmailTemplate(
        organization=organization, type=email_type, is_default=True, **default
    ).save()


def render(template, context: dict) -> tuple[str, str]:
    """(subject, body) จาก template ขององค์กร ข้อผิดพลาดของ template raise MaEmailTemplateError"""
    try:
        subject = _env.from_string(template.subject).render(context)
        body = _env.from_string(template.body).render(context)
    except TemplateError:
        logger.exception("rendering MA email template %s failed", template.id)
        raise MaEmailTemplateError(BAD_TEMPLATE_ERROR)
    return " ".join(subject.split()), body
