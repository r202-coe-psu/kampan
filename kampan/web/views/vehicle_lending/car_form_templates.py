import json

import mongoengine as me
from flask import Blueprint, abort, g, redirect, render_template, request, url_for
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import fields, validators

from kampan import models
from kampan.utils.car_form_catalog import CATALOG
from kampan.web import acl

module = Blueprint(
    "car_form_templates", __name__, url_prefix="/car_form_templates"
)

APP_VARIABLES = [
    ("app.requester_name", "ชื่อผู้ขอ"),
    ("app.division", "หน่วยงาน/ฝ่ายของผู้ขอ"),
    ("app.phone", "เบอร์โทรศัพท์"),
    ("app.location", "สถานที่ปลายทาง"),
    ("app.request_reason", "เหตุผลที่ขอใช้รถ"),
    ("app.passenger_number", "จำนวนผู้โดยสาร"),
    ("app.car_plate", "ทะเบียนรถที่จัดให้"),
    ("app.driver_name", "ชื่อพนักงานขับรถ"),
]


class CarFormTemplateForm(FlaskForm):
    name = fields.StringField(
        "ชื่อแบบฟอร์ม",
        validators=[validators.DataRequired(message="กรุณาระบุชื่อแบบฟอร์ม")],
    )
    description = fields.StringField("รายละเอียด")


class CarFormTemplateDeleteForm(FlaskForm):
    """ฟอร์มเปล่าไว้บังคับตรวจ CSRF token ของคำสั่งลบ"""


class TemplatePayloadError(ValueError):
    """ข้อมูลฟิลด์/ขั้นอนุมัติที่ client ส่งมาไม่ถูกรูปแบบ"""


def _load_list(raw, label):
    try:
        payload = json.loads(raw or "[]")
    except (TypeError, ValueError):
        raise TemplatePayloadError(f"รูปแบบข้อมูล{label}ไม่ถูกต้อง")
    if not isinstance(payload, list) or not all(isinstance(i, dict) for i in payload):
        raise TemplatePayloadError(f"รูปแบบข้อมูล{label}ไม่ถูกต้อง")
    return payload


def parse_fields_payload(raw):
    field_defs = []
    for item in _load_list(raw, "ฟิลด์"):
        choices = item.get("choices") or []
        if not isinstance(choices, list):
            raise TemplatePayloadError("รูปแบบตัวเลือกของฟิลด์ไม่ถูกต้อง")
        field_defs.append(
            models.car_form_templates.FormFieldDef(
                source=item.get("source") or "catalog",
                key=(item.get("key") or "").strip(),
                label=(item.get("label") or "").strip(),
                field_type=item.get("field_type") or None,
                choices=[str(c).strip() for c in choices if str(c).strip()],
                is_required=bool(item.get("is_required", False)),
            )
        )
    return field_defs


def parse_steps_payload(raw, organization):
    members = {m["id"]: m["user"] for m in get_org_members(organization)}
    step_defs = []
    for item in _load_list(raw, "ขั้นอนุมัติ"):
        approver_type = item.get("approver_type") or "role"
        user = None
        if approver_type == "user":
            # ตรวจฝั่ง server ว่าเป็นสมาชิก active ของ org นี้ ไม่เชื่อค่าจาก dropdown
            user = members.get(str(item.get("user") or ""))
            if user is None:
                raise TemplatePayloadError(
                    f"ผู้อนุมัติของขั้น '{item.get('label') or item.get('key') or ''}' ต้องเป็นสมาชิกของหน่วยงานนี้"
                )
        step_defs.append(
            models.car_form_templates.ApprovalStepDef(
                key=(item.get("key") or "").strip(),
                label=(item.get("label") or "").strip(),
                approver_type=approver_type,
                role=item.get("role") or None,
                user=user,
                same_division=bool(item.get("same_division", False)),
                assigns_vehicle=bool(item.get("assigns_vehicle", False)),
            )
        )
    return step_defs


def validation_message(error):
    """ข้อความที่อ่านรู้เรื่องจาก ValidationError ของ mongoengine"""
    nested = (error.errors or {}).get("__all__")
    if nested is not None:
        return getattr(nested, "message", None) or str(nested)
    if error.errors:
        return "; ".join(f"{k}: {getattr(v, 'message', v)}" for k, v in error.errors.items())
    return error.message or str(error)


def get_org_members(organization):
    roles = models.OrganizationUserRole.objects(
        organization=organization, status="active"
    )
    return [
        {
            "id": str(role.user.id),
            "name": f"{role.user.first_name} {role.user.last_name}".strip(),
            "user": role.user,
        }
        for role in roles
        if role.user
    ]


def builder_context(organization):
    return dict(
        organization=organization,
        catalog=[
            {
                "key": f.key,
                "label": f.default_label,
                "field_type": f.field_type,
                "choices": list(f.choices),
            }
            for f in CATALOG.values()
        ],
        roles=models.organizations.ORGANIZATION_ROLES,
        custom_field_types=models.car_form_templates.CUSTOM_FIELD_TYPES,
        members=[{k: v for k, v in m.items() if k != "user"} for m in get_org_members(organization)],
        app_variables=APP_VARIABLES,
    )


@module.route("/", methods=["GET"])
@acl.organization_roles_required("admin")
def index():
    organization = g.organization
    if not organization:
        abort(404)

    templates = models.car_form_templates.CarFormTemplate.objects(
        organization=organization, status="active"
    ).order_by("name")

    return render_template(
        "/vehicle_lending/car_form_templates/index.html",
        organization=organization,
        templates=templates,
        delete_form=CarFormTemplateDeleteForm(),
    )


def get_template(template_id, organization):
    """template ของ org นี้เท่านั้น (กัน IDOR ข้าม org) คืน None ถ้า id ใช้ไม่ได้"""
    try:
        return models.car_form_templates.CarFormTemplate.objects(
            id=template_id, organization=organization, status="active"
        ).first()
    except (me.ValidationError, me.errors.InvalidQueryError):
        return None


def fields_to_payload(template):
    return [
        {
            "source": f.source,
            "key": f.key,
            "label": f.label or "",
            "field_type": f.field_type or "text",
            "choices": list(f.choices),
            "is_required": f.is_required,
        }
        for f in template.fields
    ]


def steps_to_payload(template):
    return [
        {
            "key": s.key,
            "label": s.label,
            "approver_type": s.approver_type,
            "role": s.role or "",
            "user": str(s.user.id) if s.user else "",
            "same_division": s.same_division,
            "assigns_vehicle": s.assigns_vehicle,
        }
        for s in template.steps
    ]


@module.route("/create", methods=["GET", "POST"], defaults={"template_id": None})
@module.route("/<template_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def create_or_edit(template_id):
    organization = g.organization
    if not organization:
        abort(404)

    template = None
    if template_id:
        template = get_template(template_id, organization)
        if not template:
            abort(404)

    form = CarFormTemplateForm(obj=template)

    def render_form(error=None):
        return render_template(
            "/vehicle_lending/car_form_templates/create_or_edit.html",
            form=form,
            template=template,
            template_fields=fields_to_payload(template) if template else [],
            template_steps=steps_to_payload(template) if template else [],
            fields_data=request.form.get("fields_data", ""),
            steps_data=request.form.get("steps_data", ""),
            error=error,
            **builder_context(organization),
        )

    if not form.validate_on_submit():
        return render_form()

    try:
        target = template or models.car_form_templates.CarFormTemplate(
            organization=organization,
            created_by=current_user._get_current_object(),
        )
        target.name = form.name.data
        target.description = form.description.data or ""
        target.fields = parse_fields_payload(request.form.get("fields_data"))
        target.steps = parse_steps_payload(request.form.get("steps_data"), organization)
        target.last_updated_by = current_user._get_current_object()
        target.save()
    except TemplatePayloadError as error:
        return render_form(error=str(error))
    except me.ValidationError as error:
        return render_form(error=validation_message(error))

    return redirect(
        url_for(
            "vehicle_lending.car_form_templates.index",
            organization_id=organization.id,
        )
    )


@module.route("/<template_id>/delete", methods=["POST"])
@acl.organization_roles_required("admin")
def delete(template_id):
    organization = g.organization
    if not organization:
        abort(404)

    if not CarFormTemplateDeleteForm().validate_on_submit():
        abort(400, "Invalid CSRF token")

    template = get_template(template_id, organization)
    if not template:
        abort(404)

    # soft delete เพราะคำขอที่ยื่นไปแล้วอ้างถึง template นี้อยู่
    template.status = "disactive"
    template.last_updated_by = current_user._get_current_object()
    template.save()

    return redirect(
        url_for(
            "vehicle_lending.car_form_templates.index",
            organization_id=organization.id,
        )
    )
