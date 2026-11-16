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
        "enabled_modules",
        "enabled_roles",
    ],
    field_args={
        "name": {"label": "Name"},
        "description": {"label": "Desctiption"},
        # "authenticity_text": {"label": "Authenticity Text"},
    },
)


class OrganizationForm(BaseOrganizationForm):
    enabled_modules = fields.SelectMultipleField(
        "ระบบที่เปิดใช้",
        choices=models.organizations.MODULES,
        widget=widgets.ListWidget(prefix_label=False),
        option_widget=widgets.CheckboxInput(),
        validate_choice=True,
    )
    enabled_roles = fields.SelectMultipleField(
        "Role ที่เปิดใช้",
        choices=models.organizations.ORGANIZATION_ROLES,
        widget=widgets.ListWidget(prefix_label=False),
        option_widget=widgets.CheckboxInput(),
        validate_choice=True,
    )


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


DRIVER_CANNOT_APPROVE = "พนักงานขับรถเป็นผู้อนุมัติไม่ได้"


def validate_driver_is_not_approver(form, field):
    roles = field.data or []
    if "driver" in roles and any(
        role in models.organizations.RESERVATION_APPROVER_ROLE_KEYS for role in roles
    ):
        raise validators.ValidationError(DRIVER_CANNOT_APPROVE)


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
        validators=[validators.InputRequired(), validate_driver_is_not_approver],
    )


class OrganizationAddMemberForm(FlaskForm):
    members = fields.SelectMultipleField(
        "เลือกสมาชิก",
        validators=[validators.InputRequired(message="เลือกผู้ใช้อย่างน้อยหนึ่งคน")],
    )
    roles = fields.SelectMultipleField(
        "ระดับผู้ใช้งาน",
        choices=models.organizations.ORGANIZATION_ROLES,
        validators=[validators.InputRequired(), validate_driver_is_not_approver],
    )
    division = fields.SelectField(
        "สังกัดหน่วยงาน",
    )
    appointment = fields.StringField("ตำแหน่ง", validators=[])


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


UNASSIGNED_DIVISION = "none"


class OrganizationMemberSearchForm(SearchUserForm):
    start_date = fields.DateField("วันที่เพิ่ม", validators=[validators.Optional()])
    end_date = fields.DateField("ถึง", validators=[validators.Optional()])
    division = fields.SelectField(
        "แผนก",
        choices=[("", "ทั้งหมด")],
        validate_choice=False,
        validators=None,
    )

    def set_division_choices(self, divisions):
        self.division.choices = (
            [("", "ทั้งหมด"), (UNASSIGNED_DIVISION, "ยังไม่ได้ระบุแผนก")]
            + [(str(division.id), division.name) for division in divisions]
        )
