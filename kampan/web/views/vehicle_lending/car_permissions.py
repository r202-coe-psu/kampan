from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    send_file,
    abort,
    current_app,
)
from flask_login import login_required, current_user
import mongoengine as me
from flask_mongoengine import Pagination
import datetime

from kampan.web import forms, acl
from kampan import models, utils
from ... import redis_rq

module = Blueprint("car_permissions", __name__, url_prefix="/car_permissions")


@module.route("/header_page", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "head", "supervisor supplier")
def header_page():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    car_applications = models.vehicle_applications.CarApplication.objects(
        organization=organization,
        status="pending on header",
        division=current_user.get_current_division(),
    )
    paginated_car_applications = Pagination(car_applications, page=1, per_page=50)

    return render_template(
        "/vehicle_lending/car_permissions/header_page.html",
        organization=organization,
        paginated_car_applications=paginated_car_applications,
    )


@module.route("/header_approve", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "head", "supervisor supplier")
def header_approve():
    organization_id = request.form.get("organization_id")
    car_application_id = request.form.get("car_application_id")
    denied_reason = request.form.get("denied_reason", default="")

    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    car_application = models.vehicle_applications.CarApplication.objects(
        id=car_application_id
    ).first()
    car_application.status = "pending on admin"
    car_application.save()
    job = redis_rq.redis_queue.queue.enqueue(
        utils.email_utils.send_email_car_application_to_endorser,
        args=(
            car_application,
            current_user._get_current_object(),
            current_app.config,
            car_application.status,
        ),
        job_id=f"send_email_car_application_to_endorser_{car_application.id}",
        timeout=600,
        job_timeout=600,
    )
    return redirect(
        url_for(
            "vehicle_lending.car_permissions.header_page",
            organization_id=organization.id,
        )
    )


@module.route("/header_denied", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "head", "supervisor supplier")
def header_denied():
    organization_id = request.form.get("organization_id")
    car_application_id = request.form.get("car_application_id")
    denied_reason = request.form.get("denied_reason", default="")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    car_application = models.vehicle_applications.CarApplication.objects(
        id=car_application_id
    ).first()
    car_application.status = "denied by header"
    car_application.denied_reason = denied_reason
    car_application.save()

    return redirect(
        url_for(
            "vehicle_lending.car_permissions.header_page",
            organization_id=organization.id,
        )
    )


@module.route("/director_page", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "head", "supervisor supplier")
def director_page():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    car_applications = models.vehicle_applications.CarApplication.objects(
        organization=organization, status="pending on director"
    )
    paginated_car_applications = Pagination(car_applications, page=1, per_page=50)

    return render_template(
        "/vehicle_lending/car_permissions/director_page.html",
        organization=organization,
        paginated_car_applications=paginated_car_applications,
    )


@module.route("/director_approve", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "head", "supervisor supplier")
def director_approve():
    organization_id = request.form.get("organization_id")
    car_application_id = request.form.get("car_application_id")
    denied_reason = request.form.get("denied_reason", default="")

    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    car_application = models.vehicle_applications.CarApplication.objects(
        id=car_application_id
    ).first()
    car_application.status = "pending on admin"
    car_application.save()
    job = redis_rq.redis_queue.queue.enqueue(
        utils.email_utils.send_email_car_application_to_endorser,
        args=(
            car_application,
            current_user._get_current_object(),
            current_app.config,
            car_application.status,
        ),
        job_id=f"send_email_car_application_to_endorser_{car_application.id}",
        timeout=600,
        job_timeout=600,
    )
    return redirect(
        url_for(
            "vehicle_lending.car_permissions.director_page",
            organization_id=organization.id,
        )
    )


@module.route("/director_denied", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "head", "supervisor supplier")
def director_denied():
    organization_id = request.form.get("organization_id")
    car_application_id = request.form.get("car_application_id")
    denied_reason = request.form.get("denied_reason", default="")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    car_application = models.vehicle_applications.CarApplication.objects(
        id=car_application_id
    ).first()
    car_application.status = "denied by director"
    car_application.denied_reason = denied_reason
    car_application.save()

    return redirect(
        url_for(
            "vehicle_lending.car_permissions.director_page",
            organization_id=organization.id,
        )
    )


@module.route("/admin_page", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "head", "supervisor supplier")
def admin_page():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    car_applications = models.vehicle_applications.CarApplication.objects(
        organization=organization,
        status__in=["pending on admin", "denied by admin", "active"],
    ).order_by("-created_date")
    paginated_car_applications = Pagination(car_applications, page=1, per_page=50)

    return render_template(
        "/vehicle_lending/car_permissions/admin_page.html",
        organization=organization,
        paginated_car_applications=paginated_car_applications,
    )


@module.route("/admin_approve", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "head", "supervisor supplier")
def admin_approve():
    organization_id = request.form.get("organization_id")
    car_application_id = request.form.get("car_application_id")
    denied_reason = request.form.get("denied_reason", default="")

    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    car_application = models.vehicle_applications.CarApplication.objects(
        id=car_application_id
    ).first()
    car_application.status = "active"
    car_application.save()

    return redirect(
        url_for(
            "vehicle_lending.car_permissions.admin_page",
            organization_id=organization.id,
        )
    )


@module.route("/admin_denied", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "head", "supervisor supplier")
def admin_denied():
    organization_id = request.form.get("organization_id")
    car_application_id = request.form.get("car_application_id")
    denied_reason = request.form.get("denied_reason", default="")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    car_application = models.vehicle_applications.CarApplication.objects(
        id=car_application_id
    ).first()
    car_application.status = "denied by admin"
    car_application.denied_reason = denied_reason
    car_application.save()

    return redirect(
        url_for(
            "vehicle_lending.car_permissions.admin_page",
            organization_id=organization.id,
        )
    )
