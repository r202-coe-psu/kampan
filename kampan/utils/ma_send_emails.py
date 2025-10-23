from jinja2 import Template
import logging
from kampan import models
from .email_utils import PSUSMTP

logger = logging.getLogger(__name__)

email_subject_template = {
    "90d": "[แจ้งเตือน] การต่ออายุซอฟต์แวร์/บริการ ครั้งที่ 1",
    "30d": "[แจ้งเตือน] การต่ออายุซอฟต์แวร์/บริการ ครั้งที่ 2",
    "expired": "[แจ้งเตือน] การต่ออายุซอฟต์แวร์/บริการ (เลยกำหนด)",
    "default": "[แจ้งเตือน] การต่ออายุซอฟต์แวร์/บริการ",
}

# Email body template
email_body_template = """
    จากระบบงานพัสดุ (patsadu_diis@psu.ac.th) ถึงผู้เกี่ยวข้อง (ผู้รับผิดชอบ / หัวหน้าฝ่าย 
/ รองผู้บริหารแต่ละฝ่าย / หัวหน้าเจ้าหน้าที่พัสดุ / เจ้าหน้าที่พัสดุ (3 คน))

{% if notif_type == "90d" %}
เรื่อง แจ้งเตือนการต่ออายุซอฟต์แวร์/บริการ ครั้งที่ 1
เรียน ผู้เกี่ยวข้อง

    {{ name }} ที่ท่านเป็นผู้รับผิดชอบ กำลังจะหมดอายุในอีก 3 เดือนข้างหน้า
สามารถใช้งานได้ถึงวันที่ {{ end_date }} จึงขอให้ท่านวางแผนสำหรับการจัดซื้อจัดจ้างใหม่ 
และส่งเอกสารมายังงานพัสดุโดยเร็ว

{% elif notif_type == "30d" %}
เรื่อง แจ้งเตือนการต่ออายุซอฟต์แวร์/บริการ ครั้งที่ 2
เรียน ผู้เกี่ยวข้อง

    {{ name }} ที่ท่านเป็นผู้รับผิดชอบ กำลังจะหมดอายุในอีก 1 เดือนข้างหน้า
สามารถใช้งานได้ถึงวันที่ {{ end_date }} หากมีความประสงค์ที่จะดำเนินการจัดซื้อจัดจ้างใหม่
โปรดส่งเอกสารมายังงานพัสดุโดยเร็ว

{% elif notif_type == "expired" %}
เรื่อง แจ้งเตือนการต่ออายุซอฟต์แวร์/บริการ (เลยกำหนด)
เรียน ผู้เกี่ยวข้อง

    {{ name }} ที่ท่านเป็นผู้รับผิดชอบ ได้หมดอายุเมื่อวันที่ {{ end_date }} 
กรุณาดำเนินการจัดซื้อจัดจ้างใหม่โดยเร็ว เพื่อไม่ให้การใช้งานระบบหยุดชะงัก

{% endif %}

ระบบงานพัสดุ  
Link : {{ ma_url }}

ด้วยความเคารพ  
งานพัสดุ  
อีเมลติดต่อ
patsadu_diis@psu.ac.th  
"""


CATEGORY_MAP = {
    "software": "ซอฟต์แวร์",
    "product": "ครุภัณฑ์",
    "service": "จ้างเหมาบริการ",
    "material": "วัสดุ",
}


def get_procurement_email_context(procurement):
    responsible_list = []
    procurement = models.Procurement.objects(id=procurement.id).first()

    if not procurement:
        return

    due_dates = procurement.get_payment_due_dates()
    for member in procurement.responsible_by:
        division = member.division
        organization = division.organization

        # Get name and email from user or member directly
        name = (
            member.user.get_name()
            if member.user and member.user.get_name
            else member.display_name()
        )
        email = member.user.email if member.user else member.email

        if email:
            responsible_list.append(
                {
                    "name": name,
                    "email": email,
                    "organization": organization.id,
                }
            )

    text_format = {
        "product_number": procurement.product_number,
        "asset_code": procurement.asset_code,
        "name": procurement.name,
        "category": procurement.category,
        "company": procurement.company,
        "amount": procurement.amount,
        "due_date": due_dates,
        "end_date": procurement.end_date.strftime("%Y-%m-%d"),
        "responsible_by": responsible_list,
    }

    return text_format


def send_payment_notification_job(
    procurement: models.Procurement,
    notif_type,
    days_left,
    setting,
):
    logger.debug("use MA_send_mail")

    text_format = get_procurement_email_context(procurement)

    if not text_format or not text_format["responsible_by"]:
        logger.debug("No responsible_by found")
        return False

    for person in text_format["responsible_by"]:
        if not person["email"]:
            logger.debug(f"attendant {person['name']} email is required")
            return False
    try:
        psu_smtp = PSUSMTP(setting)
        if not psu_smtp.login():
            logger.debug("email cannot login")
            return False

        subject_template_str = email_subject_template.get(
            notif_type, email_subject_template["default"]
        )

        template_subject = Template(subject_template_str)
        template_body = Template(email_body_template)

        if text_format and text_format["responsible_by"]:
            for person in text_format["responsible_by"]:
                host_url = setting.get("KAMPAN_HOST_URL")
                ma_url = f"{host_url}/procurement/payment/{procurement.id}?organization_id={person['organization']}"

                context = {
                    **text_format,
                    "responsible_name": person["name"],
                    "notif_type": notif_type,
                    "days_left": days_left.get("days_left", ""),
                    "ma_url": ma_url,
                }

                email_subject = template_subject.render(context)
                email_body = template_body.render(context)

                logger.debug(f"send email to {person['email']}")
                psu_smtp.send_email(person["email"], email_subject, email_body)

                # Debug render result
                # print("\n------------------ RENDERED EMAIL ------------------")
                # print(f"To: {person['email']}")
                # print(f"Subject: {email_subject}")
                # print("Body:")
                # print(email_body)
                # print("----------------------------------------------------\n")

        psu_smtp.quit()
        return True
    except Exception as e:
        logger.error(f"send_payment_notification_job error: {e}")
        return False
