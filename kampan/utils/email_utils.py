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
        self.auth_required = setting.get("VIYYOOR_EMAIL_AUTH")

        self.server = smtplib.SMTP(self.host, self.port)

    def login(self):
        try:
            self.server.starttls()
            if self.auth_required:
                self.server.login(self.user, self.password)
            else:
                self.server.login()

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


def get_endorser_text_format(division, sender, endorser, order, endorsement_url):
    if not division or not endorser:
        return

    text_format = {
        "organization_name": division.organization.name,
        "sender_name": sender.get_name(),
        "sender_email": sender.email,
        "division_name": division.name,
        "division_description": division.description,
        "order_date": order.updated_date.strftime("%d/%m/%Y %H:%M"),
        "order_creator": order.created_by.get_name(),
        "sent_item_datetime": (
            order.sent_item_date.strftime("%d/%m/%Y %H:%M")
            if order.sent_item_date
            else "-"
        ),
        "order_objective": order.description,
        "endorser_name": endorser.get_name(),
        "endorsement_url": endorsement_url,
    }

    return text_format


def force_send_email_to_endorser(
    order,
    user,
    setting,
):
    logger.debug(f"use force_send_email_to_endorser")

    creator = order.created_by
    division = order.division
    endorser = order.head_endorser
    organization = division.organization
    email_template = organization.get_default_email_template("to endorser")

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
        division, user, endorser, order, endorsement_url
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


def force_send_email_to_supervisor_supplier(
    order,
    user,
    setting,
):
    logger.debug(f"use force_send_email_to_supervisor_supplier")

    creator = order.created_by
    division = order.division
    organization = division.organization
    endorsers = organization.get_supervisor_supplier()
    email_template = organization.get_default_email_template("to supervisor supplier")

    if not email_template:
        logger.debug(f"There are no email template for {division.name}")
        return False

    if not endorsers:
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
    endorsement_url = f"{host_url}/approve_orders/{order.id}/supervisor_supplier_approved_detail?organization_id={organization.id}"
    for endorser in endorsers:
        text_format = get_endorser_text_format(
            division, user, endorser, order, endorsement_url
        )

        email_subject = template_subject.render(text_format)
        email_body = template_body.render(text_format)

        logger.debug(f"send email to {endorser.email}")

        order_email = models.OrderEmail(
            receiver_email=endorser.email,
            sent_by=user,
            name="แจ้งเตือนการอนุมัติของหัวหน้าแผนกวัสดุ",
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


def force_send_email_to_admin(
    order,
    user,
    setting,
):
    logger.debug(f"use force_send_email_to_admin")

    creator = order.created_by
    division = order.division
    organization = division.organization
    endorser = order.admin_approver
    email_template = organization.get_default_email_template("to admin")

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
    endorsement_url = f"{host_url}/approve_orders/{order.id}/admin_approved_detail?organization_id={organization.id}"

    text_format = get_endorser_text_format(
        division, user, endorser, order, endorsement_url
    )

    email_subject = template_subject.render(text_format)
    email_body = template_body.render(text_format)

    logger.debug(f"send email to {endorser.email}")

    order_email = models.OrderEmail(
        receiver_email=endorser.email,
        sent_by=user,
        name="แจ้งเตือนการจัดการวัสดุ",
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


def force_send_email_to_staff(
    order,
    user,
    setting,
):
    logger.debug(f"use force_send_email_to_staff")

    creator = order.created_by
    division = order.division
    organization = division.organization
    endorser = order.admin_approver
    email_template = organization.get_default_email_template("to staff")

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
    endorsement_url = f""

    text_format = get_endorser_text_format(
        division, user, endorser, order, endorsement_url
    )

    email_subject = template_subject.render(text_format)
    email_body = template_body.render(text_format)

    logger.debug(f"send email to {endorser.email}")

    order_email = models.OrderEmail(
        receiver_email=endorser.email,
        sent_by=user,
        name="แจ้งเตือนวันรับพัสดุ",
    )
    order.emails.append(order_email)
    order.save()
    if psu_smtp.send_email(creator.email, email_subject, email_body):
        order.emails[-1].status = "sent"
    else:
        order.emails[-1].status = "failed"
    order.save()
    psu_smtp.quit()
    return True
