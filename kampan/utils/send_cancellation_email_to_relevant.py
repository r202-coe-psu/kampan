from jinja2 import Template
import logging
from kampan import models
from .email_utils import PSUSMTP

logger = logging.getLogger(__name__)

email_subject_template = "[แจ้งเตือน] ขออนุมัติซื้อ/จ้างพัสดุ"


email_body_template = """ 
จากระบบงานพัสดุ (patsadu_diis@psu.ac.th) ถึงผู้เกี่ยวข้อง (ผู้รับผิดชอบ / หัวหน้าฝ่าย 
/ รองผู้บริหารแต่ละฝ่าย / หัวหน้าเจ้าหน้าที่พัสดุ)

เรื่อง การยกเลิกรายการขออนุมัติซื้อ/จ้างพัสดุ

เรียน ทุกท่าน

    ตามที่ {{purchaser_name}} จาก ฝ่าย{{purchaser_division}} ได้รับอนุมัติให้ซื้อ/จ้าง ตามรายละเอียดที่เเจ้งไว้นี้

    
ใบขอซื้อ/จ้างเลขที่: {{ requisition_code }}
รายการขอซื้อ:
{% for item in items %}  
    - {{ item }}
{% endfor %}
บัดนี้ รายการดังกล่าวได้ภูกยกเลิก ระหว่างการดําเนินการ เนื่องจาก {{ note }}

จึงขอเเจ้งให้ทุกท่านทราบเเละงดดําเนินการในส่วนที่เกี่ยวข้องต่อไป

รายการขอซื้อ/จ้างพัสดุ
Link: {{ document_url }}

    ด้วยความเคารพ
      งานพัสดุ
โทร 2105, 2077, 2119
"""


# สําหรับดึงรายชื่ออีเมลผู้เกี่ยวข้องทั้งหมด
def get_revelant_user_email(requisition):
    if not requisition:
        return
    revelant_emails = set()
    # Add purchaser email
    purchaser_user = requisition.purchaser.user
    purchaser_user_email = (
        purchaser_user.email if purchaser_user and purchaser_user.email else None
    )
    if purchaser_user_email:
        revelant_emails.add(purchaser_user_email)
    # Add committees email
    if requisition.committees:
        for comittee in requisition.committees:
            logger.debug("comittee:", comittee)
            # ตรวจสอบว่า comittee.member และ comittee.member.user ไม่ใช่ None
            if not comittee.member or not comittee.member.user:
                logger.warning(
                    f"Committee member or user is None for committee: {comittee}"
                )
                continue
            comittee_user = comittee.member.user
            comittee_user_email = comittee_user.email if comittee_user.email else None
            if comittee_user_email:
                revelant_emails.add(comittee_user_email)
    # Add approver email
    if requisition.approval_history:
        for approval in requisition.approval_history:
            if not approval.approver or not approval.approver.user:
                logger.warning(f"Approver or user is None for approval: {approval}")
                continue
            approver_user = approval.approver.user
            approver_user_email = approver_user.email if approver_user.email else None
            if approver_user_email:
                revelant_emails.add(approver_user_email)

    return list(revelant_emails)


def get_email_text_format(
    requisition: models.Requisition,
    requisition_timeline: models.RequisitionTimeline,
    setting,
    user,
):
    if not requisition:
        return

    if not requisition_timeline:
        return
    purchaser_user = requisition.purchaser
    purchaser_name = purchaser_user.user.get_name() if purchaser_user else "-"
    purchaser_division = purchaser_user.division.name if purchaser_user else "-"
    requisition_code = requisition.requisition_code
    note = requisition_timeline.note if requisition_timeline.note else "-"
    host_url = setting.get("KAMPAN_HOST_URL")
    document_url = f"{host_url}/procurement/requisition_timeline"
    text_format = {
        "purchaser_name": purchaser_name,
        "purchaser_division": purchaser_division,
        "requisition_code": requisition_code,
        "items": [item.product_name for item in requisition.items],
        "note": note,
        "document_url": document_url,
    }

    return text_format


def send_cancellation_email_to_relevant(
    requisition: models.Requisition,
    requisition_timeline: models.RequisitionTimeline,
    user,
    setting,
):
    logger.debug("use send_cancellation_email_to_relevant ")

    relevant_emails = get_revelant_user_email(requisition=requisition)
    if not relevant_emails:
        logger.debug("no relevant emails found")
        return False

    text_format = get_email_text_format(
        requisition=requisition,
        requisition_timeline=requisition_timeline,
        setting=setting,
        user=user,
    )
    if not text_format:
        logger.debug("cannot get email text format")
        return False
    try:
        psu_smtp = PSUSMTP(setting)
        if not psu_smtp.login():
            return False

        email_subject = Template(email_subject_template).render(text_format)
        email_body = Template(email_body_template).render(text_format)
        # print("relevant_emails:", relevant_emails)

        for email in relevant_emails:
            try:
                # print("subject:", email_subject)
                # print("body:", email_body)
                psu_smtp.send_email(
                    to_address=email,
                    subject=email_subject,
                    body=email_body,
                )
                logger.debug(f"cancellation email sent to {email}")
            except Exception as e:
                logger.error(f"failed to send email to {email}: {e}")
        psu_smtp.quit()
        return True
    except Exception as e:
        logger.error(f"send_cancellation_email_to_relevant error: {e}")
        return False
