import mongoengine as me
import datetime

from flask_login import UserMixin
from flask import url_for

from kampan.models.organizations import ORGANIZATION_ROLES


class UserSetting(me.EmbeddedDocument):
    current_organization = me.ReferenceField("Organization", dbref=True)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )


class TemporaryUser(me.Document):
    first_name = me.StringField(required=True, max_length=256)
    last_name = me.StringField(required=True, max_length=256)
    email = me.StringField(required=True, unique=True)
    roles = me.ListField(
        me.StringField(choices=ORGANIZATION_ROLES),
        default=["staff"],
        required=True,
    )
    meta = {"collection": "temporary_users"}


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

    def has_organization_roles(self, *roles):
        if "admin" in self.roles:
            return True

        for role in roles:
            if role in self.get_current_organization_roles():
                return True
        return False

    def get_image(self):
        return ""

    def get_name(self):
        return self.get_resources_fullname_th()

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

    def get_current_organization_roles(self):
        from . import OrganizationUserRole

        try:
            org_user = OrganizationUserRole.objects(
                user=self,
                status__ne="disactive",
            ).first()
            return org_user.roles
        except:
            return []

    def is_admin_current_organization(self):
        if "admin" in self.get_current_organization_roles() or "admin" in self.roles:
            return True

        return

    def get_current_organization_create_date(self):
        from . import OrganizationUserRole

        try:
            organization_user_role = OrganizationUserRole.objects(
                user=self,
                organization=self.get_current_organization(),
                status="active",
            ).first()
            return organization_user_role.created_date

        except:
            return

    def get_current_division(self):
        from . import OrganizationUserRole

        try:
            org_division = OrganizationUserRole.objects(
                user=self,
                organization=self.get_current_organization(),
                status="active",
            ).first()
            return org_division.division

        except:
            return []

    def get_resources_fullname(self):
        try:
            if self.resources["psu"]["display_name_th"]:
                fullname = (
                    self.resources["psu"]["display_name_th"]
                    + " ( "
                    + self.resources["psu"]["display_name"]
                    + " )"
                )
            else:
                fullname = self.resources["psu"]["display_name"]
        except:
            fullname = self.get_name()
        return fullname

    def get_resources_fullname_th(self):
        try:
            if self.resources["psu"]["display_name_th"]:
                fullname = self.resources["psu"]["display_name_th"]
            else:
                fullname = self.resources["psu"]["display_name"]
        except:
            fullname = self.get_name()
        return fullname