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
        # "authenticity_text": {"label": "Authenticity Text"},
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
            file.FileAllowed(["png", "jpg", "jpeg"], "รับเฉพาะไฟล์ png เเละ jpg เท่านั้น"),
        ],
    )


class OrganizationUserForm(FlaskForm):
    users = fields.SelectMultipleField("")


class OrganizationRoleEditForm(FlaskForm):
    first_name = fields.StringField("ชื่อ (ภาษาอังกฤษ)")
    last_name = fields.StringField("ชื่อ (ภาษาอังกฤษ)")
    email = fields.StringField("อีเมล")
    appointment = fields.StringField("ตำแหน่ง", validators=[])
    roles = fields.SelectMultipleField(
        "ระดับผู้ใช้งาน",
        choices=models.organizations.ORGANIZATION_ROLES,
        validators=[validators.InputRequired()],
    )


class OrgnaizationAddMemberForm(FlaskForm):
    members = fields.SelectField(
        "เลือกสมาชิก",
    )
    roles = fields.SelectMultipleField(
        "ระดับผู้ใช้งาน",
        choices=models.organizations.ORGANIZATION_ROLES,
        validators=[validators.InputRequired()],
    )


class AdminOrganizationEditForm(BaseOrganizationForm):
    pass


class SearchUserForm(FlaskForm):
    start_date = fields.DateField(
        "เริ่มเพิ่มเมื่อวันที่",
        validators=[validators.Optional()],
    )
    end_date = fields.DateField(
        "จนถึงวันที่",
        validators=[validators.Optional()],
    )
    role = fields.SelectField(
        "ตำแหน่ง",
        choices=[("", "ทั้งหมด")] + models.organizations.ORGANIZATION_ROLES,
        validate_choice=False,
        validators=None,
        render_kw={"placeholder": "role"},
    )
    user = fields.SelectField(
        "สมาชิก",
        choices=[("", "")],
        validate_choice=False,
        validators=None,
        render_kw={"placeholder": "user"},
    )
