from flask_mongoengine.wtf import model_form
from flask_wtf import FlaskForm, file
from wtforms import fields, widgets, validators

from kampan import models

BaseOrganizationForm = model_form(
    models.Organization,
    FlaskForm,
    exclude=[
        "created_date",
        "updated_date",
        "created_by",
        "last_updated_by",
        "status",
    ],
    field_args={
        "name": {"label": "Name"},
        "description": {"label": "Desctiption"},
        "authenticity_text": {"label": "Authenticity Text"},
    },
)


class OrganizationForm(BaseOrganizationForm):
    pass


BaseLogoForm = model_form(
    models.Logo,
    FlaskForm,
    only=["logo_name"],
    field_args={
        "logo_name": {"label": "Logo Name"},
    },
)


class LogoForm(BaseLogoForm):
    uploaded_logo_file = file.FileField(
        "Logo File",
        validators=[
            file.FileAllowed(["png", "jpg"], "รับเฉพาะไฟล์ png เเละ jpg เท่านั้น"),
        ],
    )


class OrganizationUserForm(FlaskForm):
    users = fields.SelectMultipleField("")


class OrganizationRoleSelectionForm(FlaskForm):
    roles = fields.SelectMultipleField(choices=models.organizations.ORGANIZATION_ROLES)


class OrgnaizationAddMemberForm(FlaskForm):
    members = fields.SelectMultipleField("Select Members")
    role = fields.SelectField("Role", choices=models.organizations.ORGANIZATION_ROLES)


class AdminOrganizationEditForm(BaseOrganizationForm):
    pass
