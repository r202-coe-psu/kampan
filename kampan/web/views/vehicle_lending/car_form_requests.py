import datetime

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


def _parse_datetime(form, prefix):
    return datetime.datetime.strptime(
        f"{form.get(prefix + '_date', '')} {form.get(prefix + '_time', '')}",
        "%Y-%m-%d %H:%M",
    )


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


@module.route("/inbox")
@acl.organization_roles_required(*REQUEST_ROLES)
def inbox():
    organization = g.organization
    user = current_user._get_current_object()
    return render_template(
        "/vehicle_lending/car_form_requests/inbox.html",
        organization=organization,
        car_applications=utils.car_form_flow.pending_for(user, organization),
        cars=models.vehicles.Car.objects(organization=organization, status="active"),
        drivers=organization.get_all_drivers(),
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


@module.route("/new/<template_id>", methods=["GET", "POST"])
@acl.organization_roles_required(*REQUEST_ROLES)
def create(template_id):
    organization = g.organization
    template = models.car_form_templates.CarFormTemplate.objects(
        id=template_id, organization=organization, status="active"
    ).first()
    if not template:
        abort(404)

    form = request.form
    snapshot = _snapshot(template)
    details_form_class = forms.car_form_templates.build_details_form(snapshot["fields"])

    def render_form(details_form, status=200):
        return (
            render_template(
                "/vehicle_lending/car_form_requests/form.html",
                organization=organization,
                template=template,
                details_form=details_form,
                form=form,
            ),
            status,
        )

    if request.method == "GET":
        return render_form(details_form_class(formdata=None))

    details_form = details_form_class(request.form)
    if not details_form.validate():
        return render_form(details_form, 400)

    try:
        departure_datetime = _parse_datetime(form, "departure")
        return_datetime = _parse_datetime(form, "return")
    except ValueError:
        abort(400)

    member = models.OrganizationUserRole.objects(
        user=current_user.id, organization=organization, status__ne="disactive"
    ).first()

    car_application = models.vehicle_applications.CarApplication(
        organization=organization,
        form_template=template,
        template_snapshot=snapshot,
        details=details_form.details(),
        status="pending",
        current_step=0,
        creator=current_user._get_current_object(),
        updater=current_user._get_current_object(),
        division=member.division if member else None,
        phone=form.get("phone", ""),
        location=form.get("location", ""),
        request_reason=form.get("request_reason", ""),
        passenger_number=form.get("passenger_number", type=int, default=0),
        departure_datetime=departure_datetime,
        return_datetime=return_datetime,
    )
    car_application.save()
    return redirect(
        url_for(
            "vehicle_lending.car_form_requests.inbox",
            organization_id=str(organization.id),
        )
    )


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

    car = driver = None
    step = utils.car_form_flow.current_step_def(car_application)
    if step.get("assigns_vehicle"):
        car = models.vehicles.Car.objects(
            id=request.form.get("car"), organization=organization
        ).first()
        if not car:
            abort(400)
        if request.form.get("driver"):
            driver = organization.get_all_drivers().filter(
                id=request.form.get("driver")
            ).first()
            if not driver:
                abort(400)

    utils.car_form_flow.approve(
        car_application,
        current_user._get_current_object(),
        comment=request.form.get("comment", ""),
        car=car,
        driver=driver,
    )
    return redirect(
        url_for(
            "vehicle_lending.car_form_requests.inbox",
            organization_id=str(organization.id),
        )
    )


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

    utils.car_form_flow.deny(
        car_application,
        current_user._get_current_object(),
        request.form.get("denied_reason", ""),
    )
    return redirect(
        url_for(
            "vehicle_lending.car_form_requests.inbox",
            organization_id=str(organization.id),
        )
    )
