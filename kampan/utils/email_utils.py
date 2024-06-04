import datetime


import io
import base64
import copy

import PIL

from lxml import etree

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jinja2 import Environment, PackageLoader, select_autoescape, Template

import mongoengine as me
from kampan import models

import logging

logger = logging.getLogger(__name__)


class PSUSMTP:
    def __init__(self, setting):
        self.setting = setting
        self.host = setting.get("KAMPAN_EMAIL_HOST")
        self.port = setting.get("KAMPAN_EMAIL_PORT")
        self.user = setting.get("KAMPAN_EMAIL_USER")
        self.password = setting.get("KAMPAN_EMAIL_PASSWORD")
        self.server = smtplib.SMTP(self.host, self.port)

    def login(self):
        try:
            self.server.starttls()
            self.server.login(self.user, self.password)
        except Exception as e:
            logger.exception(e)
            return False
        return True

    def quit(self):
        self.server.quit()

    def send_email(self, receiver, subject, body):
        try:
            sender = self.setting.get("KAMPAN_EMAIL_USER")
            receivers = [receiver]

            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = sender
            message["To"] = receiver

            email_body = MIMEText(body, "plain")
            message.attach(email_body)

            self.server.sendmail(sender, receivers, message.as_string())

        except Exception as e:
            logger.exception(e)
            return False

        return True


# def get_creator_text_format(division, creator, order):
#     if not division or not creator or not order:
#         return

#     text_format = {
#         "organization_name": division.organization.name,
#         "division_name": division.name,
#         "division_description": division.description,
#         "creator_organization": creator.get_current_organization().name,
#     }

#     return text_format


def get_endorser_text_format(division, creator, endorser, order, endorsement_url):
    if not division or not endorser:
        return

    text_format = {
        "organization_name": division.organization.name,
        "user_name": creator.get_name(),
        "division_name": division.name,
        "division_description": division.description,
        "order_date": order.updated_date,
        "order_objective": order.description,
        "endorser_name": endorser.get_name(),
        "endorsement_url": endorsement_url,
    }

    return text_format


# def send_email_creator_in_class(
#     division,
#     setting,
# ):
#     email_template = division.order_email_template
#     if not email_template:
#         logger.debug(
#             f"there are no order email template for {division.organization.name}"
#         )

#     psu_smtp = PSUSMTP(setting)
#     if not email_template:
#         logger.debug("email template not found")
#         return False

#     if not psu_smtp.login():
#         logger.debug("PSUSMTP login failed...")
#         return False

#     orders = models.order.objects(
#         me.Q(
#             **{"emails__status": "waiting", "division": division, "status": "completed"}
#         )
#     )
#     logger.debug(
#         f"send email to creator in class { division.name } amount { orders.count() }"
#     )
#     for order in orders:
#         order.emails[-1].status = "sending"
#         order.emails[-1].updated_date = datetime.datetime.now()
#         order.save()

#         creator = order.get_creator()

#         template_subject = Template(email_template.subject)
#         template_body = Template(email_template.body)

#         text_format = get_creator_text_format(division, creator, order)
#         email_subject = template_subject.render(text_format)
#         email_body = template_body.render(text_format)

#         logger.debug(f"send email to creator {creator.email}")

#         if psu_smtp.send_email(creator.email, email_subject, email_body):
#             order.emails[-1].status = "sent"
#         else:
#             order.emails[-1].status = "failed"

#         order.emails[-1].updated_date = datetime.datetime.now()
#         order.save()

#     psu_smtp.quit()
#     return True


def send_email_endorser_in_class(
    division,
    setting,
    user,
):
    required_endorsement_email_template = (
        division.endorser_required_endorsement_email_template
    )
    without_endorsement_email_template = (
        division.endorser_without_endorsement_email_template
    )

    psu_smtp = PSUSMTP(setting)
    if not required_endorsement_email_template:
        logger.debug(
            f"there are no required endorsement email template for endorser in class {division.name}"
        )
        return False

    if not without_endorsement_email_template:
        logger.debug(
            f"there are no without endorsement email template for endorser in class {division.name}"
        )
        return False

    if not psu_smtp.login():
        logger.debug("PSUSMTP login failed...")
        return False

    logger.debug(f"send email to endorsers in class { division.name }")

    for endorser_id in division.endorsers:
        endorser = division.get_endorser_by_id(endorser_id)

        if endorser.auto_send_mail_to_endorse == "not_auto":
            continue

        if endorser.endorse_requirement == "required":
            template_subject = Template(required_endorsement_email_template.subject)
            template_body = Template(required_endorsement_email_template.body)
        else:
            template_subject = Template(without_endorsement_email_template.subject)
            template_body = Template(without_endorsement_email_template.body)

        host_url = setting.get("KAMPAN_HOST_URL")
        endorsement_url = f"{host_url}/en/classes/{division.id}?organization_id={division.organization.id}"

        text_format = get_endorser_text_format(division, endorser, endorsement_url)
        email_subject = template_subject.render(text_format)
        email_body = template_body.render(text_format)

        logger.debug(f"send email to endorser {endorser.user.email}")
        endorser.emails.create(
            receiver_email=endorser.user.email,
            status="waiting",
            sent_by=user,
            sent_date=datetime.datetime.now(),
            remark="manual send",
        )
        if psu_smtp.send_email(endorser.user.email, email_subject, email_body):
            endorser.emails[-1].status = "sent"
        else:
            endorser.emails[-1].status = "failed"
        endorser.emails[-1].updated_date = datetime.datetime.now()
    division.save()
    psu_smtp.quit()
    return True


def force_send_email_order(
    order,
    user,
    setting,
):
    creator = order.created_by
    division = order.division
    endorser = order.head_endorser
    organization = division.organization
    email_template = organization.get_default_email_template()

    if not email_template:
        logger.debug(f"There are no email template for {division.name}")
        return False

    if not endorser:
        logger.debug(f"attendant endorser is required")
        return False

    if not creator.email:
        logger.debug(f"attendant {creator.name} email is required")
        return False

    psu_smtp = PSUSMTP(setting)
    if not psu_smtp.login():
        logger.debug(f"email cannot login")
        return False

    template_subject = Template(email_template.subject)
    template_body = Template(email_template.body)

    host_url = setting.get("KAMPAN_HOST_URL")
    endorsement_url = f"{host_url}/approve_orders/{order.id}/endorser_approved_detail?organization_id={organization.id}"
    text_format = get_endorser_text_format(
        division, creator, endorser, order, endorsement_url
    )

    email_subject = template_subject.render(text_format)
    email_body = template_body.render(text_format)

    logger.debug(f"send email to {endorser.email}")

    order_email = models.OrderEmail(
        receiver_email=endorser.email, sent_by=user, name="แจ้งเตือนผู้อนุมัติระดับแผนก"
    )
    order.emails.append(order_email)
    order.save()
    if psu_smtp.send_email(endorser.email, email_subject, email_body):
        order.emails[-1].status = "sent"
    else:
        order.emails[-1].status = "failed"
    order.save()
    psu_smtp.quit()
    return True
