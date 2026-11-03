import datetime

from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user
from wtforms import fields as wtforms_fields

from kampan import models, utils
from kampan.web import acl, forms

module = Blueprint(
    "car_form_requests", __name__, url_prefix="/car_form_requests"
)

REQUEST_ROLES = (
    "admin",
    "endorser",
    "staff",
    "head",
    "director",
    "supervisor supplier",
)


def _snapshot(template):
    return {
        "fields": [dict(f.to_mongo()) for f in template.fields],
        "steps": [
            {**dict(s.to_mongo()), "user": str(s.user.id) if s.user else None}
            for s in template.steps
        ],
        "paper_file_id": str(template.paper_file.id) if template.paper_file else None,
        "placements": [dict(p.to_mongo()) for p in template.placements],
    }


def _active_car_types(organization):
    return {
        car.vehicle_type
        for car in models.vehicles.Car.objects(
            organization=organization, status="active", vehicle_type__ne=None
        )
        if car.vehicle_type
    }


@module.route("/new")
@acl.organization_roles_required(*REQUEST_ROLES)
def choose_template():
    organization = g.organization
    return render_template(
        "/vehicle_lending/car_form_requests/choose_template.html",
        organization=organization,
        templates=models.car_form_templates.CarFormTemplate.objects(
            organization=organization, status="active"
        ).order_by("name"),
    )


def _cars_requested_type_first(cars, car_application):
    requested = (car_application.details or {}).get("vehicle_kind")
    return sorted(cars, key=lambda car: car.vehicle_type != requested)


def _search_form(organization, with_status=True):
    templates = models.car_form_templates.CarFormTemplate.objects(organization=organization).order_by("name")
    return forms.car_form_requests.CarRequestSearchForm.from_args(request.args, templates, with_status)


@module.route("/")
@acl.organization_roles_required(*REQUEST_ROLES)
def index():
    organization = g.organization
    user = current_user._get_current_object()
    search_form = _search_form(organization)
    return render_template(
        "/vehicle_lending/car_form_requests/index.html",
        organization=organization,
        car_applications=utils.car_form_flow.search(
            utils.car_form_flow.visible_requests(user, organization), **search_form.search_args()
        ),
        search_form=search_form,
        current_step_def=utils.car_form_flow.current_step_def,
        step_progress=utils.car_form_flow.step_progress,
    )


@module.route("/inbox")
@acl.organization_roles_required(*REQUEST_ROLES)
def inbox():
    organization = g.organization
    user = current_user._get_current_object()
    search_form = _search_form(organization, with_status=False)
    return render_template(
        "/vehicle_lending/car_form_requests/inbox.html",
        organization=organization,
        car_applications=utils.car_form_flow.search(
            utils.car_form_flow.pending_for(user, organization), **search_form.search_args()
        ),
        search_form=search_form,
        current_step_def=utils.car_form_flow.current_step_def,
    )


@module.route("/<car_application_id>/paper")
@acl.organization_roles_required(*REQUEST_ROLES)
def paper(car_application_id):
    organization = g.organization
    car_application = models.vehicle_applications.CarApplication.objects(
        id=car_application_id, organization=organization
    ).first()
    if not car_application:
        abort(404)

    pdf = utils.car_form_paper.render_pdf(car_application)
    if pdf is None:
        abort(404)

    return Response(
        pdf,
        mimetype="application/pdf",
        headers={"Content-Disposition": "inline; filename=car_form_request.pdf"},
    )


def _request_form_class(field_defs, organization):
    car_types = _active_car_types(organization)
    return forms.car_form_templates.build_details_form(
        field_defs,
        allowed_choices={"vehicle_kind": car_types} if car_types else None,
        base=forms.car_form_requests.CarFormRequestForm,
    )


def _render_request_form(organization, template, form, car_application=None):
    return (
        render_template(
            "/vehicle_lending/car_form_requests/form.html",
            organization=organization,
            template=template,
            form=form,
            car_application=car_application,
        ),
        400 if request.method == "POST" else 200,
    )


def _apply_core_fields(car_application, form):
    car_application.details = form.details()
    car_application.phone = form.phone.data.strip()
    car_application.location = form.location.data.strip()
    car_application.request_reason = form.request_reason.data.strip()
    car_application.passenger_number = form.passenger_number.data
    car_application.departure_datetime = form.departure_datetime()
    car_application.return_datetime = form.return_datetime()
    car_application.updater = current_user._get_current_object()


@module.route("/new/<template_id>", methods=["GET", "POST"])
@acl.organization_roles_required(*REQUEST_ROLES)
def create(template_id):
    organization = g.organization
    template = models.car_form_templates.CarFormTemplate.objects(
        id=template_id, organization=organization, status="active"
    ).first()
    if not template:
        abort(404)

    snapshot = _snapshot(template)
    form = _request_form_class(snapshot["fields"], organization)()

    if not form.validate_on_submit():
        return _render_request_form(organization, template, form)

    member = models.OrganizationUserRole.objects(
        user=current_user.id, organization=organization, status__ne="disactive"
    ).first()

    car_application = models.vehicle_applications.CarApplication(
        organization=organization,
        form_template=template,
        template_snapshot=snapshot,
        status="pending",
        current_step=0,
        creator=current_user._get_current_object(),
        division=member.division if member else None,
    )
    _apply_core_fields(car_application, form)
    utils.car_form_flow.record_submitted(car_application, current_user._get_current_object())
    car_application.save()
    flash(f"ยื่นคำขอ {template.name} แล้ว", "success")
    return redirect(
        url_for(
            "vehicle_lending.car_form_requests.index",
            organization_id=str(organization.id),
        )
    )


def _saved_form_data(car_application, form_class):
    departure = car_application.departure_datetime
    return_ = car_application.return_datetime
    data = {
        "phone": car_application.phone,
        "location": car_application.location,
        "request_reason": car_application.request_reason,
        "passenger_number": car_application.passenger_number,
        "departure_date": departure.date() if departure else None,
        "departure_time": departure.time() if departure else None,
        "return_date": return_.date() if return_ else None,
        "return_time": return_.time() if return_ else None,
    }
    details = car_application.details or {}
    for key in form_class.details_keys:
        value = details.get(key)
        # details เก็บวันที่เป็น isoformat ต้องแปลงกลับให้ DateField แสดงค่าได้
        if getattr(form_class, key).field_class is wtforms_fields.DateField and isinstance(value, str):
            value = datetime.date.fromisoformat(value) if value else None
        data[key] = value
    return data


def _display_value(value):
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value)
    if isinstance(value, datetime.time):
        return value.strftime("%H:%M")
    if isinstance(value, datetime.date):
        return value.isoformat()
    return str(value).strip()


def _form_changes(form, saved):
    changes = []
    for name, old in saved.items():
        old_text, new_text = _display_value(old), _display_value(form[name].data)
        if old_text != new_text:
            changes.append(
                {"field": name, "label": str(form[name].label.text), "old": old_text, "new": new_text}
            )
    return changes


@module.route("/<car_application_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required(*REQUEST_ROLES)
def edit(car_application_id):
    organization = g.organization
    user = current_user._get_current_object()
    car_application = models.vehicle_applications.CarApplication.objects(
        id=car_application_id, organization=organization, form_template__ne=None
    ).first()
    if not car_application:
        abort(404)
    if not utils.car_form_flow.can_edit(car_application, user):
        abort(403)

    form_class = _request_form_class(
        (car_application.template_snapshot or {}).get("fields", []), organization
    )
    saved = _saved_form_data(car_application, form_class)
    form = form_class() if request.method == "POST" else form_class(data=saved)

    if not form.validate_on_submit():
        return _render_request_form(organization, car_application.form_template, form, car_application)

    changes = _form_changes(form, saved)
    if changes:
        _apply_core_fields(car_application, form)
        utils.car_form_flow.record_edited(car_application, user, changes)
        car_application.save()
        flash("บันทึกการแก้ไขคำขอแล้ว", "success")
    else:
        flash("ไม่มีข้อมูลที่เปลี่ยนแปลง", "info")
    return redirect(
        url_for(
            "vehicle_lending.car_form_requests.detail",
            car_application_id=str(car_application.id),
            organization_id=str(organization.id),
        )
    )


def _redirect_after_action(car_application, organization):
    # ทำจากหน้ารายละเอียด (next=detail) กลับไปหน้ารายละเอียด ที่เหลือกลับหน้ารายการที่ต้องอนุมัติ
    if request.form.get("next") == "detail":
        return redirect(
            url_for(
                "vehicle_lending.car_form_requests.detail",
                car_application_id=str(car_application.id),
                organization_id=str(organization.id),
            )
        )
    return redirect(
        url_for(
            "vehicle_lending.car_form_requests.inbox",
            organization_id=str(organization.id),
        )
    )


def _detail_rows(car_application):
    from kampan.utils.car_form_catalog import CATALOG

    details = car_application.details or {}
    rows = []
    for field in (car_application.template_snapshot or {}).get("fields", []):
        key = field["key"] if field.get("source") == "catalog" else f"custom_{field['key']}"
        catalog_field = CATALOG.get(field["key"]) if field.get("source") == "catalog" else None
        label = field.get("label") or (catalog_field.default_label if catalog_field else field["key"])
        value = details.get(key, "")
        if isinstance(value, (list, tuple)):
            value = ", ".join(str(v) for v in value)
        rows.append({"label": label, "value": value})
    return rows


def _step_forms(car_application, organization, formdata=None, next_page="detail"):
    step = utils.car_form_flow.current_step_def(car_application)
    cars = _cars_requested_type_first(
        models.vehicles.Car.objects(organization=organization, status="active"), car_application
    )
    approve_form = forms.car_form_requests.ApproveStepForm.for_step(
        step, cars, organization.get_all_drivers(), formdata=formdata, next_page=next_page
    )
    deny_form = forms.car_form_requests.DenyStepForm(formdata=formdata, next=next_page)
    return approve_form, deny_form


def _render_detail(car_application, organization, approve_form=None, deny_form=None, open_modal="", status=200):
    user = current_user._get_current_object()
    can_act = utils.car_form_flow.can_act(car_application, user, organization)
    if can_act and approve_form is None:
        approve_form, deny_form = _step_forms(car_application, organization)
    return (
        render_template(
            "/vehicle_lending/car_form_requests/detail.html",
            organization=organization,
            car_application=car_application,
            can_act=can_act,
            can_edit=utils.car_form_flow.can_edit(car_application, user),
            approve_form=approve_form,
            deny_form=deny_form,
            open_modal=open_modal,
            detail_rows=_detail_rows(car_application),
            audit_logs=list(reversed(car_application.audit_logs)),
            current_step_def=utils.car_form_flow.current_step_def,
            step_progress=utils.car_form_flow.step_progress,
        ),
        status,
    )


@module.route("/<car_application_id>")
@acl.organization_roles_required(*REQUEST_ROLES)
def detail(car_application_id):
    organization = g.organization
    user = current_user._get_current_object()
    car_application = models.vehicle_applications.CarApplication.objects(
        id=car_application_id, organization=organization, form_template__ne=None
    ).first()
    if not car_application or not utils.car_form_flow.can_view(car_application, user, organization):
        abort(404)

    return _render_detail(car_application, organization)


@module.route("/<car_application_id>/approve", methods=["POST"])
@acl.organization_roles_required(*REQUEST_ROLES)
def approve(car_application_id):
    organization = g.organization
    car_application = models.vehicle_applications.CarApplication.objects(
        id=car_application_id, organization=organization
    ).first()
    if not car_application:
        abort(404)

    if not utils.car_form_flow.can_act(
        car_application, current_user._get_current_object(), organization
    ):
        abort(403)

    approve_form, deny_form = _step_forms(
        car_application, organization, formdata=request.form, next_page=request.form.get("next", "")
    )
    if not approve_form.validate():
        return _render_detail(
            car_application, organization, approve_form, forms.car_form_requests.DenyStepForm(formdata=None),
            open_modal=f"approve-{car_application.id}", status=400,
        )

    car = driver = None
    if "car" in approve_form:
        car = models.vehicles.Car.objects(id=approve_form.car.data, organization=organization).first()
        if approve_form.driver.data:
            driver = organization.get_all_drivers().filter(id=approve_form.driver.data).first()

    utils.car_form_flow.approve(
        car_application,
        current_user._get_current_object(),
        comment=(approve_form.comment.data or "").strip(),
        car=car,
        driver=driver,
    )
    flash("อนุมัติคำขอแล้ว", "success")
    return _redirect_after_action(car_application, organization)


@module.route("/<car_application_id>/deny", methods=["POST"])
@acl.organization_roles_required(*REQUEST_ROLES)
def deny(car_application_id):
    organization = g.organization
    car_application = models.vehicle_applications.CarApplication.objects(
        id=car_application_id, organization=organization
    ).first()
    if not car_application:
        abort(404)

    if not utils.car_form_flow.can_act(
        car_application, current_user._get_current_object(), organization
    ):
        abort(403)

    deny_form = forms.car_form_requests.DenyStepForm(formdata=request.form)
    if not deny_form.validate():
        approve_form, _ = _step_forms(car_application, organization, formdata=None)
        return _render_detail(
            car_application, organization, approve_form, deny_form,
            open_modal=f"deny-{car_application.id}", status=400,
        )

    utils.car_form_flow.deny(
        car_application,
        current_user._get_current_object(),
        deny_form.denied_reason.data.strip(),
    )
    flash("ไม่อนุมัติคำขอแล้ว", "success")
    return _redirect_after_action(car_application, organization)
