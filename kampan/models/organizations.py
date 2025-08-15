import mongoengine as me
import datetime
import markdown
import json

from flask import url_for, request
from kampan import models

ORGANIZATION_ROLES = [
    ("staff", "พนักงาน"),
    ("endorser", "ผู้มีสิทธิ์อนุมัติ"),
    ("head", "หัวหน้าฝ่าย"),
    ("supervisor supplier", "หัวหน้าฝ่ายบริหารจัดการ"),
    ("admin", "ผู้ดูแล/เจ้าหน้าที่พัสดุ"),
]

ORGANIZATION_USER_ROLE_STATUS = [
    ("active", "เข้าสู่ระบบแล้ว"),
    ("disactive", "นำออกแล้ว"),
    ("pending", "รอการเข้าสู่ระบบ"),
]


class OrganizationUserRole(me.Document):
    meta = {"collection": "organization_user_roles"}

    organization = me.ReferenceField("Organization", dbref=True, required=True)
    division = me.ReferenceField("Division", dbref=True)
    user = me.ReferenceField("User", dbref=True)
    roles = me.ListField(
        me.StringField(choices=ORGANIZATION_ROLES), default=["staff"], required=True
    )

    first_name = me.StringField(default="")
    last_name = me.StringField(default="")
    email = me.StringField(default="")
    appointment = me.StringField(default="")

    last_ip_address = me.StringField()
    status = me.StringField(default="active", choices=ORGANIZATION_USER_ROLE_STATUS)

    added_by = me.ReferenceField("User", dbref=True, required=True)
    last_modifier = me.ReferenceField("User", dbref=True, required=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )

    def display_roles(self):
        roles = []
        for role in self.roles:
            for organization_role, display_role in ORGANIZATION_ROLES:
                if role == organization_role:
                    roles.append(display_role)
        return " ,".join(roles)

    def display_fullname(self):
        if self.user:
            return self.user.get_resources_fullname()
        return self.first_name + " " + self.last_name

    def display_name(self):
        return self.first_name + " " + self.last_name

    def display_user_fullname(self):
        if self.user:
            return self.user.get_resources_fullname_th()
        return self.first_name + " " + self.last_name

    def display_email(self):
        if self.user:
            return self.user.email
        return self.email

    def display_appointment(self):
        if len(self.appointment) >= 30:
            return self.appointment[:30] + "..."

        return self.appointment


class Organization(me.Document):
    meta = {"collection": "organizations"}

    name = me.StringField(min_length=4, max_length=255, required=True)
    description = me.StringField()
    # authenticity_text = me.StringField(required=True, default="")

    status = me.StringField(required=True, default="active")

    created_by = me.ReferenceField("User", dbref=True)
    last_updated_by = me.ReferenceField("User", dbref=True)

    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )

    def get_description(self):
        return markdown.markdown(self.description)

    def get_distinct_users(self):
        if OrganizationUserRole.objects().count():
            return (
                OrganizationUserRole.objects(organization=self, status="active")
                .order_by("-first_name")
                .distinct(field="user")
            )

    def get_organization_users(self, division=None):
        if OrganizationUserRole.objects().count():
            if not division:
                return OrganizationUserRole.objects(
                    organization=self, status__ne="disactive"
                ).order_by("-first_name")
            return OrganizationUserRole.objects(
                organization=self, status__ne="disactive", division=division
            ).order_by("-first_name")

    def get_logo(self):
        return Logo.objects(organization=self, marked_as_organization_logo=True).first()

    def get_logo_picture(self):
        logo = Logo.objects(organization=self, marked_as_organization_logo=True).first()
        if logo:
            return url_for(
                "organizations.download_logo",
                organization_id=self.id,
                logo_id=logo.id,
                filename=logo.logo_file.filename,
                thumbnail="thumbnail",
            )

        return url_for("static", filename="images/globe.png")

    def get_logos(self):
        return models.Logo.objects(organization=self).order_by("-id")

    def get_logo_ids(self):
        return [
            str(l.id) for l in models.Logo.objects(organization=self).order_by("-id")
        ]

    def get_url_download_logo_images(self, format=""):
        logos = models.Logo.objects(organization=self)
        data = []

        for logo in logos:
            data.append(
                dict(
                    id=str(logo.id),
                    uri=url_for(
                        "organizations.download_logo",
                        organization_id=self.id,
                        logo_id=logo.id,
                        thumbnail="thumbnail",
                        filename=logo.logo_file.filename,
                    ),
                )
            )

        if format == "json":
            return json.dumps(data)

        return data

    def get_classes(self):
        return models.Class.objects(organization=self, status="active").order_by("-id")

    def get_endorsers(self):
        endorsers_in_org = models.OrganizationUserRole.objects(
            organization=self, roles__in=["endorser"], status="active"
        )
        user_ids = [endorser.user.id for endorser in endorsers_in_org]
        return models.User.objects(id__in=user_ids)

    def get_admins(self):
        endorsers_in_org = models.OrganizationUserRole.objects(
            organization=self, roles__in=["admin"], status="active"
        )
        user_ids = [endorser.user.id for endorser in endorsers_in_org]
        return models.User.objects(id__in=user_ids)

    def get_default_email_template(self, email_type):
        try:
            email_template = models.EmailTemplate.objects(
                organization=self, is_default=True, type=email_type
            ).first()
        except:
            email_template = models.EmailTemplate.objects(
                organization=self, is_default=True
            ).first()
        return email_template

    def get_supervisor_supplier(self):
        endorsers_in_org = models.OrganizationUserRole.objects(
            organization=self, roles__in=["supervisor supplier"], status="active"
        )
        user_ids = [endorser.user.id for endorser in endorsers_in_org]
        return models.User.objects(id__in=user_ids)

    def get_director(self):
        division = models.Division.objects(name="ฝ่ายบริหาร").first()
        endorsers = division.get_header()
        user_ids = [endorser.user.id for endorser in endorsers]
        return models.User.objects(id__in=user_ids)


class Logo(me.Document):
    meta = {"collection": "logos"}

    organization = me.ReferenceField("Organization", dbref=True, required=True)
    logo_name = me.StringField(required=True, max_length=256)
    logo_file = me.ImageField(
        required=True,
        collection_name="logo_fs",
        size=(3840, 2160, False),
        thumbnail_size=(1920, 1920, False),
    )

    uploaded_by = me.ReferenceField("User", dbref=True)
    uploaded_date = me.DateTimeField(required=True, default=datetime.datetime.now)

    last_updated_by = me.ReferenceField("User", dbref=True)
    updated_date = me.DateTimeField(required=True, default=datetime.datetime.now)

    marked_as_organization_logo = me.BooleanField(default=False)
