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
from kampan import models, default_settings
from kampan.utils.email_layout import render_email_html

import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def get_host_url(setting):
    """URL ของ environment ที่รันอยู่ (staging/prod) สำหรับใส่ลิงก์ในอีเมล"""
    host_url = (setting or {}).get("KAMPAN_HOST_URL") or default_settings.KAMPAN_HOST_URL
    return host_url.rstrip("/")


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

    def send_email(self, receiver, subject, body, html=False, steps=None):
        try:
            sender = self.sender
            if self.sender_name:
                sender = formataddr((self.sender_name, self.sender))

            receivers = [receiver]

            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = sender
            message["To"] = receiver

            message.attach(MIMEText(body, "plain", "utf-8"))
            if html:
                message.attach(
                    MIMEText(render_email_html(subject, body, steps), "html", "utf-8")
                )

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
        "order_creator_email": order.created_by.email,
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

    host_url = get_host_url(setting)
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
    if psu_smtp.send_email(endorser.email, email_subject, email_body, html=True):
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

    host_url = get_host_url(setting)
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
        if psu_smtp.send_email(endorser.email, email_subject, email_body, html=True):
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

        host_url = get_host_url(setting)
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
        if psu_smtp.send_email(admin.email, email_subject, email_body, html=True):
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

    host_url = get_host_url(setting)
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
    if psu_smtp.send_email(creator.email, email_subject, email_body, html=True):
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
        "lost_break_item_date": lost_break_item.created_date.strftime("%d/%m/%Y %H:%M"),
        "lost_break_item_creator": lost_break_item.user.get_name(),
        "lost_break_item_email": lost_break_item.user.email,
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

    host_url = get_host_url(setting)
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
        psu_smtp.send_email(endorser.email, email_subject, email_body, html=True)

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
        "car": (
            car_application.car.license_plate
            if car_application.car
            else "รอเจ้าหน้าที่จัดรถ"
        ),
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
    logger.info(f"use force_send_email_to_endorser")

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

    host_url = get_host_url(setting)
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
        print(f"----> send email to {endorser.email}")
        psu_smtp.send_email(endorser.email, email_subject, email_body, html=True)
    logger.debug(
        "################ Finished sending emails to all endorsers ################"
    )
    psu_smtp.quit()
    return True


def get_car_application_result_text_format(
    division, sender, car_application, application_url
):
    status_labels = dict(models.vehicle_applications.CAR_APPLICATION_STATUS)
    is_denied = car_application.status.startswith("denied")
    driver = car_application.driver

    return {
        "organization_name": division.organization.name if division else "-",
        "division_name": division.name if division else "-",
        "order_name": car_application.creator.get_name(),
        "order_email": car_application.creator.email,
        "status_label": status_labels.get(car_application.status, car_application.status),
        "denied_reason": (car_application.denied_reason or "-") if is_denied else "-",
        "departure_datetime": car_application.departure_datetime.strftime("%d/%m/%Y %H:%M"),
        "return_datetime": (
            car_application.return_datetime.strftime("%d/%m/%Y %H:%M")
            if car_application.return_datetime
            else "-"
        ),
        "location": car_application.location or "-",
        "car_application_objective": car_application.request_reason,
        "car": (
            car_application.car.license_plate
            if car_application.car
            else "รอเจ้าหน้าที่จัดรถ"
        ),
        "driver_name": driver.get_name() if driver else "-",
        "sender_name": sender.get_name(),
        "sender_email": sender.email,
        "application_url": application_url,
    }


def get_car_application_steps(car_application):
    """ขั้นตอนอนุมัติของใบขอใช้รถ พร้อมสถานะของแต่ละขั้น สำหรับ stepper ในอีเมล"""
    approvers = [("header", "หัวหน้าฝ่าย"), ("admin", "พัสดุ")]
    if car_application.using_type == "out of town":
        approvers.append(("director", "ผอ."))

    status = car_application.status
    keys = [key for key, _ in approvers]
    denied = status.startswith("denied by ")
    stage = status.removeprefix("denied by ").removeprefix("pending on ")
    if status in ("active", "completed"):
        reached = len(keys)
    elif stage in keys:
        reached = keys.index(stage)
    else:
        return []

    steps = [{"label": "ยื่นคำขอ", "state": "done"}]
    for index, (_, label) in enumerate(approvers):
        if index < reached:
            state = "done"
        elif index == reached:
            state = "denied" if denied else "current"
        else:
            state = "upcoming"
        steps.append({"label": label, "state": state})
    steps.append(
        {"label": "อนุมัติ", "state": "done" if reached == len(keys) else "upcoming"}
    )
    return steps


def send_email_car_application_to_requester(car_application, user, setting):
    """แจ้งผู้ขอทุกครั้งที่ใบขอใช้รถถูกอนุมัติไปขั้นถัดไปหรือถูกปฏิเสธ"""
    creator = car_application.creator
    organization = car_application.organization
    email_template = organization.get_default_email_template("car_application_result")

    if not email_template:
        logger.debug("There are no car_application_result email template")
        return False

    if not creator or not creator.email:
        logger.debug("car application creator email is required")
        return False

    division = car_application.division or creator.get_current_division()
    application_url = (
        f"{get_host_url(setting)}/vehicle_lending/car_applications"
        f"?organization_id={organization.id}"
    )
    text_format = get_car_application_result_text_format(
        division, user, car_application, application_url
    )
    email_subject = Template(email_template.subject).render(text_format)
    email_body = Template(email_template.body).render(text_format)

    psu_smtp = PSUSMTP(setting)
    if not psu_smtp.login():
        logger.debug("email cannot login")
        return False

    logger.debug(f"send car application result to {creator.email}")
    sent = psu_smtp.send_email(
        creator.email,
        email_subject,
        email_body,
        html=True,
        steps=get_car_application_steps(car_application),
    )
    psu_smtp.quit()
    return sent
