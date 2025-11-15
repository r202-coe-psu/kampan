from jinja2 import Template
import logging
from kampan import models
from .email_utils import PSUSMTP

logger = logging.getLogger(__name__)

email_subject_template = {
    "head": "[แจ้งผล] การพิจารณาอนุมัติรายการขอซื้อ/จ้าง จากหัวหน้าฝ่าย",
    "manager": "[แจ้งผล] การพิจารณาอนุมัติรายการขอซื้อ/จ้าง จากผู้บริหาร",
    "default": "[แจ้งผล] การพิจารณาอนุมัติรายการขอซื้อ/จ้าง",
}

email_body_template = """เรียน ผู้เกี่ยวข้อง

    ตามที่ {{ purchaser_name }} ได้ขอซื้อ/จ้างผ่านระบบ ใบขอซื้อเลขที่: {{ requisition_code }}

ผลการพิจารณาจาก{{ notif_type }} : ไม่อนุมัติ
เหตุผล : {{ rejected_reason }}

ระบบขอซื้อพัสดุ 
Link: {{ document_url }}

ด้วยความเคารพ
งานพัสดุ
"""
ROLES_MAP = {
    "head": "หัวหน้าฝ่าย",
    "manager": "ผู้บริหาร",
}


def get_email_text_format(requisition, setting, notif_type=None):
    # Get committee members grouped by type and position
    specification_members = []
    procurement_members = []
    inspection_members = []
    rejected_reason = []

    req = models.Requisition.objects(id=requisition.id).first()
    if not req:
        return

    # Get purchaser info
    purchaser = req.purchaser

    user = purchaser.user if purchaser and purchaser.user else None

    purchaser_name = (
        user.get_name() if user else purchaser.display_name() if purchaser else "-"
    )
    purchaser_email = user.email if user else purchaser.email if purchaser else "-"
    host_url = setting.get("KAMPAN_HOST_URL")
    document_url = f"{host_url}/procurement/requisitions/{requisition.id}/document"

    for history in requisition.approval_history:
        if history.action == "rejected" and history.approver_role == notif_type:
            rejected_reason.append(history.reason)

    for committee in requisition.committees:
        if not committee.member:
            continue

        member = committee.member
        name = (
            member.user.get_name()
            if member.user and member.user.get_name
            else member.display_name()
        )
        email = member.user.email if member.user else member.email

        if committee.committee_type == "specification":
            specification_members.append(
                {
                    "name": name,
                    "email": email,
                }
            )
        elif committee.committee_type == "procurement":
            procurement_members.append(
                {
                    "name": name,
                    "email": email,
                }
            )
        elif committee.committee_type == "inspection":
            inspection_members.append(
                {
                    "name": name,
                    "email": email,
                }
            )

    text_format = {
        "requisition_code": requisition.requisition_code,
        "purchaser_name": purchaser_name,
        "purchaser_email": purchaser_email,
        "specification_members": specification_members,
        "procurement_members": procurement_members,
        "inspection_members": inspection_members,
        "document_url": document_url,
        "notif_type": ROLES_MAP.get(notif_type, "ผู้บริหาร"),
        "rejected_reason": " ".join(rejected_reason),
    }
    return text_format


def send_email_rejected_to_user_admin_committee(
    requisition: models.Requisition,
    user_id,
    setting,
    organization,
    notif_type,
):
    logger.debug("use send_email_rejected_to_user_admin_committee")
    all_admins = organization.get_admins()
    text_format = get_email_text_format(requisition, setting, notif_type)

    if not text_format:
        logger.debug("No text format found")
        return False

    purchaser_email = text_format["purchaser_email"]
    if not purchaser_email or purchaser_email == "-":
        logger.debug("Purchaser email not found")
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

        # Render email body
        email_subject = template_subject.render(text_format)
        email_body = template_body.render(text_format)

        logger.debug(f"send email to {purchaser_email}")
        psu_smtp.send_email(purchaser_email, email_subject, email_body)

        # Debug render result
        # print("\n" + "=" * 50)
        # print("RENDERED EMAIL - PURCHASER")
        # print("=" * 50)
        # print(f"To: {purchaser_email}")
        # print(f"Subject: {email_subject}")
        # print("Body:")
        # print(email_body)
        # print("=" * 50 + "\n")

        # Also send to committee members
        all_committee_members = (
            text_format["specification_members"]
            + text_format["procurement_members"]
            + text_format["inspection_members"]
        )

        # Remove duplicates by email
        unique_members = {}
        for member in all_committee_members:
            if member["email"] and member["email"] != "-":
                unique_members[member["email"]] = member

        for member_email in unique_members.items():
            try:
                logger.debug(f"send email to {member_email}")
                psu_smtp.send_email(member_email, email_subject, email_body)
            except Exception as e:
                logger.error(f"Error sending email to {member_email}: {e}")
                continue

        for admin in all_admins:
            if not admin.email:
                continue
            try:
                logger.debug(f"send email to {admin.email}")
                psu_smtp.send_email(admin.email, email_subject, email_body)
            except Exception as e:
                logger.error(f"Error sending email to {admin.email}: {e}")
                continue

        psu_smtp.quit()
        return True
    except Exception as e:
        logger.error(f"send_email_approve_to_user_admin_committee error: {e}")
        return False
