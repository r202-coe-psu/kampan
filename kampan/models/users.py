import mongoengine as me
import datetime

from flask_login import UserMixin
from flask import url_for


class UserSetting(me.EmbeddedDocument):
    current_organization = me.ReferenceField("Organization", dbref=True)
    updated_date = me.DateTimeField(required=True, default=datetime.datetime.now)


class User(me.Document, UserMixin):
    username = me.StringField(min_length=5, max_length=64)
    email = me.StringField(required=True, unique=True)
    password = me.StringField(required=True, default="")
    first_name = me.StringField(required=True, max_length=256)
    last_name = me.StringField(required=True, max_length=256)
    status = me.StringField(required=True, default="active")
    roles = me.ListField(me.StringField(), default=["user"])
    citizen_id = me.StringField(max_length=13)
    student_id = me.StringField(max_length=10)

    picture_url = me.StringField(max_length=500)
    picture = me.ImageField(
        thumbnail_size=(800, 600, True), collection_name="user_picture"
    )

    biography = me.StringField(max_length=500)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )

    user_setting = me.EmbeddedDocumentField("UserSetting", default=UserSetting)
    metadata = me.DictField()
    resources = me.DictField()

    meta = {"collection": "users"}

    @property
    def organizations(self):
        from . import OrganizationUserRole

        return [
            organization
            for organization in OrganizationUserRole.objects(user=self, status="active")
            .only("organization")
            .distinct("organization")
        ]

    def has_roles(self, roles):
        for role in roles:
            if role in self.roles:
                return True

        return False

    def get_image(self):
        return ""

    def get_name(self):
        return self.first_name + " " + self.last_name

    def get_picture(self):
        if self.picture:
            return url_for(
                "accounts.picture", user_id=self.id, filename=self.picture.filename
            )
        # if "google" in self.resources:
        #     return self.resources["google"].get("picture", "")
        # return url_for("static", filename="images/user.png")

    def get_current_organization(self):
        if not self.organizations:
            return

        if not self.user_setting.current_organization and self.organizations:
            return self.organizations[0]

        return self.user_setting.current_organization
