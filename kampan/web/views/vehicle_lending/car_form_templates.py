import io
import json

import mongoengine as me
from PyPDF2 import PdfReader
from flask import (
    Blueprint,
    Response,
    abort,
    g,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import fields, validators

from kampan import models
from kampan.utils.car_form_catalog import CATALOG
from kampan.utils.car_form_paper import APPROVAL_PARTS, available_variables, sample_values
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
    ("app.car_type", "ประเภทรถที่จัด"),
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


class PaperForm(FlaskForm):
    """ฟอร์มเปล่าไว้ตรวจ CSRF token ของการอัปโหลด PDF และบันทึกตำแหน่งตัวแปร"""


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


INVISIBLE_CHARS = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"))


def clean_key(raw):
    # ค่าที่ copy มาวางมักติด zero-width space ซึ่ง strip() ไม่ตัดให้; รูปแบบ key ตรวจใน model
    return str(raw or "").translate(INVISIBLE_CHARS).strip().lower()


def parse_fields_payload(raw):
    field_defs = []
    for item in _load_list(raw, "ฟิลด์"):
        choices = item.get("choices") or []
        if not isinstance(choices, list):
            raise TemplatePayloadError("รูปแบบตัวเลือกของฟิลด์ไม่ถูกต้อง")
        field_defs.append(
            models.car_form_templates.FormFieldDef(
                source=item.get("source") or "catalog",
                key=clean_key(item.get("key")),
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
    for index, item in enumerate(_load_list(raw, "ขั้นอนุมัติ"), start=1):
        approver_type = item.get("approver_type") or "role"
        user = None
        user_id = str(item.get("user") or "")
        if approver_type == "user" and user_id:
            # ตรวจฝั่ง server ว่าเป็นสมาชิก active ของ org นี้ ไม่เชื่อค่าจาก dropdown
            user = members.get(user_id)
            if user is None:
                raise TemplatePayloadError(
                    f"ขั้นที่ {index}: ผู้อนุมัติต้องเป็นสมาชิกของหน่วยงานนี้"
                )
        step_defs.append(
            models.car_form_templates.ApprovalStepDef(
                key=clean_key(item.get("key")),
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
    """รายการปัญหาภาษาไทยจาก ValidationError ของ mongoengine (ไม่ส่งข้อความดิบให้ผู้ใช้)"""
    if isinstance(error, models.car_form_templates.CarFormTemplateInvalid):
        return error.problems
    nested = (error.errors or {}).get("__all__")
    if isinstance(nested, models.car_form_templates.CarFormTemplateInvalid):
        return nested.problems
    if nested is not None:
        return [getattr(nested, "message", None) or str(nested)]
    return ["ข้อมูลแบบฟอร์มไม่ถูกต้อง กรุณาตรวจสอบฟิลด์และขั้นอนุมัติอีกครั้ง"]


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
        return render_form(error=[str(error)])
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


MAX_PDF_BYTES = 10 * 1024 * 1024


class PaperUploadError(ValueError):
    """ไฟล์ PDF ที่อัปโหลดใช้ไม่ได้"""


def read_pdf_upload(upload):
    """คืน (bytes, page_sizes) ถ้าเป็น PDF ที่อ่านได้และไม่เกินขนาดที่กำหนด"""
    content = upload.read(MAX_PDF_BYTES + 1) if upload else b""
    if not content:
        raise PaperUploadError("กรุณาเลือกไฟล์ PDF")
    if len(content) > MAX_PDF_BYTES:
        raise PaperUploadError("ไฟล์ PDF ต้องมีขนาดไม่เกิน 10 MB")
    if not content.lstrip().startswith(b"%PDF"):
        raise PaperUploadError("ไฟล์ที่อัปโหลดต้องเป็น PDF")
    try:
        reader = PdfReader(io.BytesIO(content))
        page_sizes = [
            [float(page.mediabox.width), float(page.mediabox.height)]
            for page in reader.pages
        ]
    except Exception:
        raise PaperUploadError("อ่านไฟล์ PDF ไม่ได้ ไฟล์อาจเสียหาย")
    if not page_sizes:
        raise PaperUploadError("ไฟล์ PDF ไม่มีหน้า")
    return content, page_sizes


APPROVAL_PART_LABELS = {
    "name": "ชื่อผู้อนุมัติ",
    "date": "วันที่อนุมัติ",
    "decision": "ผลการพิจารณา",
    "comment": "ความเห็น",
}
APP_DATE_GROUPS = [
    ("departure", "วันเวลาออกเดินทาง"),
    ("return", "วันเวลากลับ"),
    ("created", "วันที่ยื่นคำขอ"),
]
APP_DATE_PARTS = [
    ("day", "วันที่"),
    ("month_th", "เดือน"),
    ("year_be", "ปี พ.ศ."),
    ("time", "เวลา"),
]


def variable_catalog(template):
    """ตัวแปรที่วางบนกระดาษได้ พร้อมป้ายชื่อและตัวเลือก (ใช้กับ check placement) เรียงตามชื่อ"""
    labels = dict(APP_VARIABLES)
    labels["org.name"] = "ชื่อหน่วยงาน"
    for group, group_label in APP_DATE_GROUPS:
        for part, part_label in APP_DATE_PARTS:
            labels[f"app.{group}.{part}"] = f"{group_label} : {part_label}"

    choices = {}
    for field in template.fields:
        name = f"details.{field.details_key()}"
        catalog_field = CATALOG.get(field.key) if field.source == "catalog" else None
        labels[name] = field.label or (catalog_field.default_label if catalog_field else field.key)
        options = field.choices or (list(catalog_field.choices) if catalog_field else [])
        if options:
            choices[name] = list(options)
    for step in template.steps:
        for part in APPROVAL_PARTS:
            name = f"approvals.{step.key}.{part}"
            labels[name] = f"{step.label} : {APPROVAL_PART_LABELS[part]}"
        choices[f"approvals.{step.key}.decision"] = ["approved", "denied"]

    samples = sample_values(template)
    return [
        {
            "name": name,
            "label": labels.get(name, name),
            "choices": choices.get(name, []),
            "sample": samples.get(name, ""),
        }
        for name in sorted(available_variables(template))
    ]


def placements_to_payload(template):
    return [
        {
            "page": p.page,
            "x": p.x,
            "y": p.y,
            "w": p.w,
            "h": p.h,
            "variable": p.variable,
            "kind": p.kind,
            "match_value": p.match_value or "",
            "font_size": p.font_size,
            "align": p.align,
        }
        for p in template.placements
    ]


def render_paper_editor(template, organization, error=None, status=200):
    paper_file = template.paper_file
    return (
        render_template(
            "/vehicle_lending/car_form_templates/paper_editor.html",
            template=template,
            organization=organization,
            error=error,
            form=PaperForm(),
            paper_file=paper_file,
            variables=variable_catalog(template),
            placements=placements_to_payload(template),
            page_sizes=paper_file.page_sizes if paper_file else [],
        ),
        status,
    )


@module.route("/<template_id>/paper_editor", methods=["GET"])
@acl.organization_roles_required("admin")
def paper_editor(template_id):
    organization = g.organization
    if not organization:
        abort(404)

    template = get_template(template_id, organization)
    if not template:
        abort(404)

    return render_paper_editor(template, organization)


@module.route("/<template_id>/paper_file", methods=["POST"])
@acl.organization_roles_required("admin")
def upload_paper_file(template_id):
    organization = g.organization
    if not organization:
        abort(404)

    if not PaperForm().validate_on_submit():
        abort(400, "Invalid CSRF token")

    template = get_template(template_id, organization)
    if not template:
        abort(404)

    upload = request.files.get("pdf")
    try:
        content, page_sizes = read_pdf_upload(upload)
    except PaperUploadError as error:
        return render_paper_editor(template, organization, error=str(error), status=400)

    paper_file = models.car_form_templates.CarFormPaperFile(
        organization=organization,
        filename=upload.filename,
        data=content,
        page_count=len(page_sizes),
        page_sizes=page_sizes,
        uploaded_by=current_user._get_current_object(),
    )
    paper_file.save()

    # เอกสารเดิมยังอยู่ เพราะ snapshot ของคำขอที่ยื่นไปแล้วชี้ id เดิม
    template.paper_file = paper_file
    template.last_updated_by = current_user._get_current_object()
    template.save()

    return redirect(
        url_for(
            "vehicle_lending.car_form_templates.paper_editor",
            template_id=template.id,
            organization_id=organization.id,
        )
    )


@module.route("/<template_id>/paper_file", methods=["GET"])
@acl.organization_roles_required("admin")
def download_paper_file(template_id):
    organization = g.organization
    if not organization:
        abort(404)

    template = get_template(template_id, organization)
    if not template or not template.paper_file:
        abort(404)

    return Response(
        bytes(template.paper_file.data),
        mimetype="application/pdf",
        headers={"Content-Disposition": "inline"},
    )


def parse_placements_payload(raw):
    placements = []
    for item in _load_list(raw, "ตำแหน่งตัวแปร"):
        try:
            placements.append(
                models.car_form_templates.PaperPlacement(
                    page=int(item.get("page", 0)),
                    x=float(item["x"]),
                    y=float(item["y"]),
                    w=float(item["w"]),
                    h=float(item["h"]),
                    variable=str(item.get("variable") or ""),
                    kind=item.get("kind") or "text",
                    match_value=str(item.get("match_value") or ""),
                    font_size=float(item.get("font_size") or 14),
                    align=item.get("align") or "left",
                )
            )
        except (KeyError, TypeError, ValueError):
            raise TemplatePayloadError("รูปแบบข้อมูลตำแหน่งตัวแปรไม่ถูกต้อง")
    return placements


@module.route("/<template_id>/placements", methods=["POST"])
@acl.organization_roles_required("admin")
def save_placements(template_id):
    organization = g.organization
    if not organization:
        abort(404)

    if not PaperForm().validate_on_submit():
        abort(400, "Invalid CSRF token")

    template = get_template(template_id, organization)
    if not template:
        abort(404)

    try:
        template.placements = parse_placements_payload(request.form.get("placements_data"))
        template.last_updated_by = current_user._get_current_object()
        template.save()
    except (TemplatePayloadError, me.ValidationError) as error:
        message = (
            validation_message(error)
            if isinstance(error, me.ValidationError)
            else str(error)
        )
        template.reload()
        return render_paper_editor(template, organization, error=message, status=400)

    return redirect(
        url_for(
            "vehicle_lending.car_form_templates.paper_editor",
            template_id=template.id,
            organization_id=organization.id,
        )
    )
