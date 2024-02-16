import mongoengine as me
import datetime
import bson

from kampan import models

ENDORSER_POSITIONS = [
    ("endorser_1", "Endorser 1"),
    ("endorser_2", "Endorser 2"),
    ("endorser_3", "Endorser 3"),
    ("endorser_4", "Endorser 4"),
    ("endorser_5", "Endorser 5"),
]


class EndorserEmail(me.EmbeddedDocument):
    receiver_email = me.StringField(required=True)
    status = me.StringField(required=True, default="not_sent")
    sent_date = me.DateTimeField()
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )
    sent_by = me.ReferenceField("User", dbref=True)
    remark = me.StringField(default="")


class Endorser(me.EmbeddedDocument):
    endorser_id = me.StringField(
        required=True,
        choices=ENDORSER_POSITIONS,
    )
    user = me.ReferenceField("User", dbref=True, required=True)
    name = me.StringField(required=True, max_length=256)

    position = me.StringField()

    emails = me.EmbeddedDocumentListField(EndorserEmail)

    auto_send_mail_to_endorse = me.StringField(required=True, default="auto")

    last_updated_by = me.ReferenceField("User", dbref=True, required=True)
    updated_date = me.DateTimeField(
        required=True, auto_now=True, default=datetime.datetime.now
    )

    def get_email_status(self):
        return [email.status for email in self.emails]


class Division(me.Document):
    meta = {"collection": "divisions"}

    name = me.StringField(required=True, max_length=256)
    description = me.StringField()
    status = me.StringField(required=True, default="active")
    endorsers = me.MapField(field=me.EmbeddedDocumentField(Endorser))

    organization = me.ReferenceField("Organization", dbref=True)
    created_by = me.ReferenceField("User", dbref=True)
    last_updated_by = me.ReferenceField("User", dbref=True)

    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )

    def get_distinct_users(self):
        return (
            models.OrganizationUserRole.objects(
                organization=self.organization,
                status="active",
                division=self,
            )
            .order_by("-first_name")
            .distinct(field="user")
        )

    def get_division_users(self):
        return models.OrganizationUserRole.objects(
            organization=self.organization,
            status="active",
            division=self,
        ).order_by("-first_name")
