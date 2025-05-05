from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    send_file,
    abort,
)
from flask_login import login_required, current_user
import mongoengine as me
from flask_mongoengine import Pagination
import datetime

from kampan.web import forms, acl
from kampan import models

module = Blueprint(
    "motorcycle_permissions", __name__, url_prefix="/motorcycle_permissions"
)


@module.route("/admin_page", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "head", "supervisor supplier")
def admin_page():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    motorcycle_applications = models.vehicle_applications.MotorcycleApplication.objects(
        organization=organization,
        status__nin=["disactive"],
    ).order_by("-created_date")
    paginated_motorcycle_applications = Pagination(
        motorcycle_applications, page=1, per_page=50
    )

    return render_template(
        "/vehicle_lending/motorcycle_permissions/admin_page.html",
        organization=organization,
        paginated_motorcycle_applications=paginated_motorcycle_applications,
    )


@module.route("/admin_approve", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "head", "supervisor supplier")
def admin_approve():
    organization_id = request.form.get("organization_id")
    motorcycle_application_id = request.form.get("motorcycle_application_id")
    denied_reason = request.form.get("denied_reason", default="")

    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    motorcycle_application = models.vehicle_applications.MotorcycleApplication.objects(
        id=motorcycle_application_id
    ).first()
    motorcycle_application.status = "active"
    motorcycle_application.save()

    return redirect(
        url_for(
            "vehicle_lending.motorcycle_permissions.admin_page",
            organization_id=organization.id,
        )
    )


@module.route("/admin_denied", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "head", "supervisor supplier")
def admin_denied():
    organization_id = request.form.get("organization_id")
    motorcycle_application_id = request.form.get("motorcycle_application_id")
    denied_reason = request.form.get("denied_reason", default="")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    motorcycle_application = models.vehicle_applications.MotorcycleApplication.objects(
        id=motorcycle_application_id
    ).first()
    motorcycle_application.status = "denied"
    motorcycle_application.denied_reason = denied_reason
    motorcycle_application.save()

    return redirect(
        url_for(
            "vehicle_lending.motorcycle_permissions.admin_page",
            organization_id=organization.id,
        )
    )
