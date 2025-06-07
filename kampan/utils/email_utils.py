import datetime


import io
import base64
import copy

import PIL

from lxml import etree

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
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
        self.sender = setting.get("KAMPAN_EMAIL_SENDER")
        self.password = setting.get("KAMPAN_EMAIL_PASSWORD")
        self.auth_required = setting.get("KAMPAN_EMAIL_AUTH")
        self.sender_name = setting.get("KAMPAN_EMAIL_SENDER_NAME")

        if not self.sender:
            self.sender = self.user

        self.server = smtplib.SMTP(self.host, self.port)

    def login(self):
        try:
            self.server.starttls()
            if self.auth_required:
                self.server.login(self.user, self.password)

        except Exception as e:
            logger.exception(e)
            return False
        return True

    def quit(self):
        self.server.quit()

    def send_email(self, receiver, subject, body):
        try:
            sender = self.sender
            if self.sender_name:
                sender = formataddr((self.sender_name, self.sender))

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
        "order_email": order.created_by.email,
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
    organization = order.organization
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
    endorsement_url = (
        f"{host_url}/approve_orders/endorser?organization_id={organization.id}"
    )
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
    endorsement_url = f"{host_url}/approve_orders/supervisor_supplier?organization_id={organization.id}"
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
    all_admins = organization.get_admins()
    email_template = organization.get_default_email_template("to admin")

    if not email_template:
        logger.debug(f"There are no email template for {division.name}")
        return False

    if not creator.email:
        logger.debug(f"attendant {creator.name} email is required")
        return False

    psu_smtp = PSUSMTP(setting)
    if not psu_smtp.login():
        logger.debug(f"email cannot login")
        return False

    for admin in all_admins:
        if not admin.email:
            pass
        template_subject = Template(email_template.subject)
        template_body = Template(email_template.body)

        host_url = setting.get("KAMPAN_HOST_URL")
        endorsement_url = (
            f"{host_url}/approve_orders/admin?organization_id={organization.id}"
        )

        text_format = get_endorser_text_format(
            division, user, admin, order, endorsement_url
        )

        email_subject = template_subject.render(text_format)
        email_body = template_body.render(text_format)

        logger.debug(f"send email to {admin.email}")

        order_email = models.OrderEmail(
            receiver_email=admin.email,
            sent_by=user,
            name="แจ้งเตือนการจัดการวัสดุ",
        )
        order.emails.append(order_email)
        order.save()
        if psu_smtp.send_email(admin.email, email_subject, email_body):
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
    endorser = organization.get_admins()[0]
    email_template = organization.get_default_email_template("to staff")

    if not email_template:
        logger.debug(f"There are no email template for {division.name}")
        return False

    # if not endorser:
    #     logger.debug(f"attendant endorser is required")
    #     return False

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

    logger.debug(f"send email to {creator.email}")

    order_email = models.OrderEmail(
        receiver_email=creator.email,
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


def get_send_email_lost_break_text_format(
    organization, sender, endorser, lost_break_item, endorsement_url
):
    if not endorser:
        return

    text_format = {
        "organization_name": organization.name,
        "sender_name": sender.get_name(),
        "sender_email": sender.email,
        "supervisor_supplier_name": endorser.get_name(),
        "lost_break_item_date": lost_break_item.updated_date.strftime("%d/%m/%Y %H:%M"),
        "lost_break_item_creator": lost_break_item.created_by.get_name(),
        "lost_break_item_objective": lost_break_item.description,
        "lost_break_item_name": lost_break_item.item.name,
        "lost_break_item_quantity": lost_break_item.quantity,
        "endorser_name": endorser.get_name(),
        "endorsement_url": endorsement_url,
    }

    return text_format


def send_email_lost_break(
    lost_break_item,
    user,
    setting,
):
    logger.debug(f"use send_email_lost_break")

    creator = lost_break_item.user
    organization = lost_break_item.organization
    endorsers = organization.get_supervisor_supplier()
    email_template = organization.get_default_email_template("lost_break")

    if not email_template:
        logger.debug(f"There are no email template")
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
    endorsement_url = (
        f"{host_url}/lost_breaks/approve_page?organization_id={organization.id}"
    )
    for endorser in endorsers:
        text_format = get_send_email_lost_break_text_format(
            organization, user, endorser, lost_break_item, endorsement_url
        )

        email_subject = template_subject.render(text_format)
        email_body = template_body.render(text_format)

        logger.debug(f"send email to {endorser.email}")
        psu_smtp.send_email(endorser.email, email_subject, email_body)

    psu_smtp.quit()
    return True


def get_car_application_text_format(
    division, sender, endorser, car_application, endorsement_url
):
    if not endorser:
        return

    text_format = {
        "organization_name": division.organization.name,
        "sender_name": sender.get_name(),
        "sender_email": sender.email,
        "order_name": car_application.creator.get_name(),
        "order_email": car_application.creator.email,
        "division_name": division.name,
        "departure_datetime": car_application.departure_datetime.strftime(
            "%d/%m/%Y %H:%M"
        ),
        "car_application_objective": car_application.request_reason,
        "car": car_application.car.license_plate,
        "endorser_name": endorser.get_name(),
        "endorsement_url": endorsement_url,
    }

    return text_format


def send_email_car_application_to_endorser(
    car_application,
    user,
    setting,
    state,
):
    logger.debug(f"use force_send_email_to_endorser")

    creator = car_application.creator
    division = creator.get_current_division()
    organization = division.organization

    if state == "pending on header":
        endorsers = division.get_user_endorsers()
        # print("-----> header", endorsers)

    elif state == "pending on director":
        endorsers = organization.get_director()
        # print("-----> director", endorsers)
    elif state == "pending on admin":
        endorsers = organization.get_admins()
        # print("-----> admin", endorsers)
    email_template = organization.get_default_email_template("car_application")

    if not email_template:
        logger.debug(f"There are no email template")
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
    if state == "pending on header":
        endorsement_url = f"{host_url}/vehicle_lending/car_permissions/header_page?organization_id={organization.id}"
    elif state == "pending on director":
        endorsement_url = f"{host_url}/vehicle_lending/car_permissions/director_page?organization_id={organization.id}"
    elif state == "pending on admin":
        endorsement_url = f"{host_url}/vehicle_lending/car_permissions/admin_page?organization_id={organization.id}"

    logger.debug("################ Ready to send email to endorsers ################")
    for endorser in endorsers:
        text_format = get_car_application_text_format(
            division, user, endorser, car_application, endorsement_url
        )

        email_subject = template_subject.render(text_format)
        email_body = template_body.render(text_format)

        logger.debug(f"send email to {endorser.email}")
        psu_smtp.send_email(endorser.email, email_subject, email_body)
    logger.debug(
        "################ Finished sending emails to all endorsers ################"
    )
    psu_smtp.quit()
    return True
