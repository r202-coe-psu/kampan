from flask import (
    Blueprint,
    render_template,
    request,
    abort,
)

from kampan.web import acl
from kampan import models

module = Blueprint("car_manuals", __name__, url_prefix="/car_manuals")


@module.route("", methods=["GET"])
@acl.organization_roles_required(
    "admin",
    "endorser",
    "staff",
    "head",
    "supervisor supplier",
    "driver",
    "director",
    "manager",
)
def index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    if not organization:
        return abort(404)

    return render_template(
        "/vehicle_lending/car_manuals/index.html",
        organization=organization,
    )
