import datetime

import mongoengine as me
from flask import url_for
from flask_login import UserMixin

from kampan.models.organizations import ORGANIZATION_ROLES


class UserSetting(me.EmbeddedDocument):
    current_organization = me.ReferenceField("Organization", dbref=True)
    updated_date = me.DateTimeField(required=True, default=datetime.datetime.now, auto_now=True)


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
    picture = me.ImageField(thumbnail_size=(800, 600, True), collection_name="user_picture")

    biography = me.StringField(max_length=500)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(required=True, default=datetime.datetime.now, auto_now=True)
    last_login_date = me.DateTimeField()

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

    def get_selectable_organizations(self):
        from . import Organization

        if "admin" in self.roles:
            return list(Organization.objects(status="active").order_by("name"))

        return self.organizations

    def is_member_of(self, organization):
        if not organization:
            return False

        if "admin" in self.roles:
            return True

        from . import OrganizationUserRole

        return bool(
            OrganizationUserRole.objects(
                user=self,
                organization=organization,
                status__ne="disactive",
            ).first()
        )

    def get_viewing_organization(self):
        from flask import g, has_request_context

        if has_request_context():
            organization = getattr(g, "organization", None)
            if organization:
                return organization

        return self.get_current_organization()

    def get_organization_roles(self, organization=None):
        from . import OrganizationUserRole

        if organization is None:
            organization = self.get_viewing_organization()

        if not organization:
            return []

        org_user = OrganizationUserRole.objects(
            user=self,
            organization=organization,
            status__ne="disactive",
        ).first()

        return org_user.roles if org_user else []

    def get_organization_role_labels(self, organization=None):

        role_labels = dict(ORGANIZATION_ROLES)

        return [role_labels.get(role, role) for role in self.get_organization_roles(organization)]

    def has_organization_roles(self, *roles, organization=None):
        if "admin" in self.roles:
            return True

        user_roles = self.get_organization_roles(organization)
        for role in roles:
            if role in user_roles:
                return True
        return False

    def get_image(self):
        return ""

    def get_name(self):
        return self.get_resources_fullname_th()

    def get_picture(self):
        if self.picture:
            return url_for("accounts.picture", user_id=self.id, filename=self.picture.filename)
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

        return self.get_organization_roles()

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

    def get_current_division(self, organization=None):
        from . import OrganizationUserRole

        if organization is None:
            organization = self.get_viewing_organization()

        if not organization:
            return []

        try:
            org_division = OrganizationUserRole.objects(
                user=self,
                organization=organization,
                status="active",
            ).first()
            return org_division.division

        except:
            return []

    def get_resources_fullname(self):
        try:
            if self.resources["psu"]["display_name_th"]:
                fullname = self.resources["psu"]["display_name_th"] + " ( " + self.resources["psu"]["display_name"] + " )"
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
            fullname = self.first_name + " " + self.last_name
        return fullname

    def get_first_name_th(self):
        try:
            if self.resources["psu"]["first_name_th"]:
                first_name = self.resources["psu"]["first_name_th"]
            else:
                first_name = self.resources["psu"]["first_name_th"]
        except:
            first_name = self.first_name
        return first_name

    def get_last_name_th(self):
        try:
            if self.resources["psu"]["first_name_th"]:
                last_name = self.resources["psu"]["last_name_th"]
            else:
                last_name = self.resources["psu"]["last_name_th"]
        except:
            last_name = self.last_name
        return last_name

    def get_current_organization_user_role(self):
        from . import OrganizationUserRole

        try:
            organization_user_role = OrganizationUserRole.objects(
                user=self,
                organization=self.get_current_organization(),
                status="active",
            ).first()
            return organization_user_role

        except:
            return

    def is_admin_organization(self):
        if "admin" in self.roles:
            return True

        if "admin" in self.get_current_organization_roles():
            return True

    def is_supervisor_supplier_organization(self):
        if "admin" in self.roles:
            return True

        if "admin" in self.get_current_organization_roles():
            return True

        if "supervisor supplier" in self.get_current_organization_roles():
            return True

    def is_directer_organization(self):
        division = self.get_current_division()

        if "admin" in self.roles:
            return True

        if "admin" in self.get_current_organization_roles():
            return True

        division_name = ""
        if division:
            division_name = division.name

        if "head" in self.get_current_organization_roles() and division_name == "ฝ่ายบริหาร":
            return True
