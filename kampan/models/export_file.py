import mongoengine as me
import datetime

STATUS_CHOICES = [
    ("waiting", "Waiting"),
    ("processing", "Processing"),
    ("completed", "Completed"),
    ("incomplete", "Incomplete"),
    ("failed", "Failed"),
    ("disable", "Disable"),
]


class ExportFile(me.Document):
    meta = {"collection": "export_documents"}
    file = me.FileField()
    file_name = me.StringField(required=True)
    status = me.StringField(
        choices=STATUS_CHOICES, default=STATUS_CHOICES[0][0], required=True
    )
    type_ = me.StringField(required=True)
    created_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )
    created_by = me.ReferenceField("User", dbref=True, required=True)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )
