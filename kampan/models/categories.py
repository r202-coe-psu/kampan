import mongoengine as me
import datetime
from kampan import models


class Category(me.Document):
    meta = {"collection": "categories"}

    name = me.StringField(required=True, max_length=256)
    description = me.StringField()
    organization = me.ReferenceField("Organization", dbref=True)

    status = me.StringField(default="active", required=True)
    last_updated_by = me.ReferenceField("User", dbref=True)
    created_by = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )

    def get_count_item(self):
        count = models.Item.objects(
            categories=self, status__ne="disactive", organization=self.organization
        ).count()
        return count
