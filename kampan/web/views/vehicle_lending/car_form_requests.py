import datetime

from flask import Blueprint, abort, g, redirect, request, url_for
from flask_login import current_user

from kampan import models, utils
from kampan.web import acl

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
        "paper_html": template.paper_html,
    }


@module.route("/new/<template_id>", methods=["POST"])
@acl.organization_roles_required(*REQUEST_ROLES)
def create(template_id):
    organization = g.organization
    template = models.car_form_templates.CarFormTemplate.objects(
        id=template_id, organization=organization, status="active"
    ).first()
    if not template:
        abort(404)

    form = request.form
    member = models.OrganizationUserRole.objects(
        user=current_user.id, organization=organization, status__ne="disactive"
    ).first()

    car_application = models.vehicle_applications.CarApplication(
        organization=organization,
        form_template=template,
        template_snapshot=_snapshot(template),
        status="pending",
        current_step=0,
        creator=current_user._get_current_object(),
        updater=current_user._get_current_object(),
        division=member.division if member else None,
        phone=form.get("phone", ""),
        location=form.get("location", ""),
        request_reason=form.get("request_reason", ""),
        passenger_number=form.get("passenger_number", type=int, default=0),
        departure_datetime=datetime.datetime.strptime(
            f"{form['departure_date']} {form['departure_time']}", "%Y-%m-%d %H:%M"
        ),
        return_datetime=datetime.datetime.strptime(
            f"{form['return_date']} {form['return_time']}", "%Y-%m-%d %H:%M"
        ),
    )
    car_application.save()
    return redirect(
        url_for(
            "vehicle_lending.car_applications.index",
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
            driver = models.User.objects(id=request.form.get("driver")).first()

    utils.car_form_flow.approve(
        car_application,
        current_user._get_current_object(),
        comment=request.form.get("comment", ""),
        car=car,
        driver=driver,
    )
    return redirect(
        url_for(
            "vehicle_lending.car_applications.index",
            organization_id=str(organization.id),
        )
    )
