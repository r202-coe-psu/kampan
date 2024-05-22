import mongoengine as me
import datetime
import markdown
import json

from flask import url_for, request
from kampan import models

ORGANIZATION_ROLES = [
    ("staff", "พนักงาน"),
    ("endorser", "ผู้มีสิทธิ์อนุญาต"),
    ("supervisor", "หัวหน้าแผนก"),
    ("supervisor supplier", "หัวหน้าพัสดุ"),
    ("admin", "ผู้ดูแล/เจ้าหน้าที่พัสดุ"),
]


class OrganizationUserRole(me.Document):
    meta = {"collection": "organization_user_roles"}

    organization = me.ReferenceField("Organization", dbref=True, required=True)
    division = me.ReferenceField("Division", dbref=True)
    user = me.ReferenceField("User", dbref=True, required=True)
    roles = me.ListField(
        me.StringField(choices=ORGANIZATION_ROLES), default=["staff"], required=True
    )

    last_ip_address = me.StringField()
    status = me.StringField(default="active")

    added_by = me.ReferenceField("User", dbref=True, required=True)
    last_modifier = me.ReferenceField("User", dbref=True, required=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )


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

    def get_organization_users(self):
        if OrganizationUserRole.objects().count():
            return OrganizationUserRole.objects(
                organization=self, status="active"
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
            organization=self, role__in=["endorser"], status="active"
        )
        user_ids = [endorser.user.id for endorser in endorsers_in_org]
        return models.User.objects(id__in=user_ids)

    def get_default_email_template(self):
        email_template = models.EmailTemplate.objects(
            organization=self, is_default=True
        ).first()
        return email_template


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
