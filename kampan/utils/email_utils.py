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


def get_participant_text_format(class_, participant, certificate):
    if not class_ or not participant or not certificate:
        return

    text_format = {
        "organization_name": class_.organization.name,
        "class_name": class_.name,
        "class_printed_name": class_.printed_name,
        "class_description": class_.description,
        "class_started_date": class_.started_date,
        "class_ended_date": class_.ended_date,
        "class_issued_date": class_.issued_date,
        "participant_name": participant.name,
        "participant_group": participant.get_group_display(),
        "participant_commond_id": participant.common_id,
        "participant_organization": participant.organization,
        "participant_certificate_class_date": class_.class_date_text,
        "participant_certificate_url": certificate.validated_url,
    }

    return text_format


def get_endorser_text_format(class_, endorser, endorsement_url):
    if not class_ or not endorser:
        return

    text_format = {
        "organization_name": class_.organization.name,
        "class_name": class_.name,
        "class_printed_name": class_.printed_name,
        "class_description": class_.description,
        "class_started_date": class_.get_started_date_display(),
        "class_ended_date": class_.get_ended_date_display(),
        "class_issued_date": class_.issued_date,
        "class_organization": class_.organization,
        "endorser_name": endorser.name,
        "endorsement_url": endorsement_url,
    }

    return text_format


def send_email_participant_in_class(
    class_,
    setting,
):
    email_template = class_.certificate_email_template
    if not email_template:
        logger.debug(
            f"there are no certificate email template for {class_.organization.name}"
        )

    psu_smtp = PSUSMTP(setting)
    if not email_template:
        logger.debug("email template not found")
        return False

    if not psu_smtp.login():
        logger.debug("PSUSMTP login failed...")
        return False

    certificates = models.Certificate.objects(
        me.Q(**{"emails__status": "waiting", "class_": class_, "status": "completed"})
    )
    logger.debug(
        f"send email to participant in class { class_.name } amount { certificates.count() }"
    )
    for certificate in certificates:
        certificate.emails[-1].status = "sending"
        certificate.emails[-1].updated_date = datetime.datetime.now()
        certificate.save()

        participant = certificate.get_participant()

        template_subject = Template(email_template.subject)
        template_body = Template(email_template.body)

        text_format = get_participant_text_format(class_, participant, certificate)
        email_subject = template_subject.render(text_format)
        email_body = template_body.render(text_format)

        logger.debug(f"send email to participant {participant.email}")

        if psu_smtp.send_email(participant.email, email_subject, email_body):
            certificate.emails[-1].status = "sent"
        else:
            certificate.emails[-1].status = "failed"

        certificate.emails[-1].updated_date = datetime.datetime.now()
        certificate.save()

    psu_smtp.quit()
    return True


def send_email_endorser_in_class(
    class_,
    setting,
    user,
):
    required_endorsement_email_template = (
        class_.endorser_required_endorsement_email_template
    )
    without_endorsement_email_template = (
        class_.endorser_without_endorsement_email_template
    )

    psu_smtp = PSUSMTP(setting)
    if not required_endorsement_email_template:
        logger.debug(
            f"there are no required endorsement email template for endorser in class {class_.name}"
        )
        return False

    if not without_endorsement_email_template:
        logger.debug(
            f"there are no without endorsement email template for endorser in class {class_.name}"
        )
        return False

    if not psu_smtp.login():
        logger.debug("PSUSMTP login failed...")
        return False

    logger.debug(f"send email to endorsers in class { class_.name }")

    for endorser_id in class_.endorsers:
        endorser = class_.get_endorser_by_id(endorser_id)

        if endorser.auto_send_mail_to_endorse == "not_auto":
            continue

        if endorser.endorse_requirement == "required":
            template_subject = Template(required_endorsement_email_template.subject)
            template_body = Template(required_endorsement_email_template.body)
        else:
            template_subject = Template(without_endorsement_email_template.subject)
            template_body = Template(without_endorsement_email_template.body)

        host_url = setting.get("CERTIFICATE_HOST_URL")
        endorsement_url = f"{host_url}/en/classes/{class_.id}?organization_id={class_.organization.id}"

        text_format = get_endorser_text_format(class_, endorser, endorsement_url)
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
    class_.save()
    psu_smtp.quit()
    return True


def force_send_email_certificate(
    certificate,
    setting,
):
    participant = certificate.get_participant()
    class_ = certificate.class_
    email_template = class_.certificate_email_template

    if not email_template:
        logger.debug(f"There are no email template for {class_.name}")
        return False

    if not participant.email:
        logger.debug(f"attendant {participant.name} email is required")
        return False

    psu_smtp = PSUSMTP(setting)
    if not psu_smtp.login():
        logger.debug(f"email cannot login")
        return False

    template_subject = Template(email_template.subject)
    template_body = Template(email_template.body)

    text_format = get_participant_text_format(class_, participant, certificate)

    email_subject = template_subject.render(text_format)
    email_body = template_body.render(text_format)

    logger.debug(f"send email to {participant.email}")

    if psu_smtp.send_email(participant.email, email_subject, email_body):
        certificate.emails[-1].status = "sent"
        certificate.save()
        psu_smtp.quit()
        return True

    certificate.emails[-1].status = "failed"
    certificate.save()
    psu_smtp.quit()
    return False
