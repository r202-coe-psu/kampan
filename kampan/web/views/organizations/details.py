from flask import Blueprint, render_template

from kampan.web import acl
from kampan import models

module = Blueprint("details", __name__, url_prefix="/<organization_id>/details")


@module.route("/")
@acl.organization_roles_required("admin")
def index(organization_id):
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()

    return render_template(
        "/organizations/detail.html",
        organization=organization,
    )
