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
CATEGORY_CHOICES = [
    ("mas", "MAS"),
    ("ma", "MA"),
    ("unknown", "Unknown"),
]


class Document(me.Document):
    meta = {"collection": "documents"}
    file = me.FileField()
    category = me.StringField(
        choices=CATEGORY_CHOICES, default=CATEGORY_CHOICES[2][0], required=True
    )
    status = me.StringField(
        choices=STATUS_CHOICES, default=STATUS_CHOICES[0][0], required=True
    )

    created_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )
    created_by = me.ReferenceField("User", dbref=True, required=True)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )
    updated_by = me.ReferenceField("User", dbref=True, required=True)
