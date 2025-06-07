import mongoengine as me
import datetime
import bson

from kampan import models


class Division(me.Document):
    meta = {"collection": "divisions"}

    name = me.StringField(required=True, max_length=256)
    description = me.StringField(default="")
    status = me.StringField(required=True, default="active")

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

    def get_endorsers(self):
        return models.OrganizationUserRole.objects(
            organization=self.organization,
            status="active",
            roles__in=["endorser", "head"],
            division=self,
        ).order_by("-first_name")

    def get_header(self):
        return models.OrganizationUserRole.objects(
            organization=self.organization,
            status="active",
            roles__in=["head"],
            division=self,
        ).order_by("-first_name")

    def get_user_endorsers(self):
        endorsers = models.OrganizationUserRole.objects(
            organization=self.organization,
            status="active",
            roles__in=["endorser", "head"],
            division=self,
        ).order_by("-first_name")
        user_ids = [endorser.user.id for endorser in endorsers]
        return models.User.objects(id__in=user_ids)
