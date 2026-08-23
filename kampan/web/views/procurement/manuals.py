from flask import (
    Blueprint,
    g,
    render_template,
    abort,
)
from flask_login import login_required

from kampan.web import acl

module = Blueprint("manuals", __name__, url_prefix="/manuals")


@module.route("", methods=["GET"])
@login_required
@acl.organization_roles_required(
    "admin",
    "endorser",
    "staff",
    "head",
    "supervisor supplier",
    "manager",
    "director",
)
def index():
    organization = g.organization

    if not organization:
        return abort(404)

    return render_template(
        "/procurement/requisitions/manual.html",
        organization=organization,
    )

