import mongoengine as me
import datetime
import bson

PARTICIPANT_GROUP = [
    ("attendance", "Attendance"),
    ("pass_examination", "Pass Examination"),
    ("participant", "Participant"),
    ("achievement", "Achievement"),
    ("winner", "Winner"),
    ("first_runner_up", "First Runner-up"),
    ("second_runner_up", "Second Runner-up"),
    ("honorable_mention_prize", "Honorable Mention Prize"),
    ("advisor", "Advisor"),
]

ENDORSER_POSITIONS = [
    ("endorser_1", "Endorser 1"),
    ("endorser_2", "Endorser 2"),
    ("endorser_3", "Endorser 3"),
    ("endorser_4", "Endorser 4"),
    ("endorser_5", "Endorser 5"),
]


class Participant(me.EmbeddedDocument):
    id = me.ObjectIdField(required=True, default=bson.ObjectId)
    common_id = me.StringField(required=True, max_length=256)
    name = me.StringField(required=True, max_length=256)
    email = me.StringField(max_length=256)
    group = me.StringField(
        required=True,
        choices=PARTICIPANT_GROUP,
    )
    organization = me.StringField(max_length=256, default="")

    last_updated_by = me.ReferenceField("User", dbref=True, required=True)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )

    extra = me.DictField()


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
    endorse_requirement = me.StringField(required=True, default="required")
    auto_send_mail_to_endorse = me.StringField(required=True, default="auto")

    last_updated_by = me.ReferenceField("User", dbref=True, required=True)
    updated_date = me.DateTimeField(
        required=True, auto_now=True, default=datetime.datetime.now
    )

    # def get_signature(self):
    #     from .signatures import Signature

    #     return Signature.objects(owner=self.user).order_by("-id").first()

    def get_email_status(self):
        return [email.status for email in self.emails]


class Warehouse(me.Document):
    meta = {"collection": "warehouses"}

    name = me.StringField(required=True, max_length=256)
    printed_name = me.StringField(required=True)
    description = me.StringField()
    organization = me.ReferenceField("Organization", dbref=True)

    instructors = me.ListField(me.StringField())
    participants = me.MapField(field=me.EmbeddedDocumentField(Participant))
    allow_duplicate_participant = me.StringField(required=True, default="not_allowed")

    endorsers = me.MapField(field=me.EmbeddedDocumentField(Endorser))
    endorse_method = me.StringField(required=True, default="user")

    auto_send_mail_participant = me.StringField(required=True, default="auto")

    issued_date = me.DateTimeField(required=True, default=datetime.datetime.now)

    started_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    ended_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    warehouse_date_text = me.StringField(max_length=500, default="")

    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )

    owner = me.ReferenceField("User", dbref=True, required=True)

    status = me.StringField(default="active")

    certificate_email_template = me.ReferenceField(
        "EmailTemplate", dbref=True, require=True
    )
    endorser_required_endorsement_email_template = me.ReferenceField(
        "EmailTemplate", dbref=True, require=True
    )
    endorser_without_endorsement_email_template = me.ReferenceField(
        "EmailTemplate", dbref=True, require=True
    )
