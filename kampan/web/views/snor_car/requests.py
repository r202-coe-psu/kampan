from flask import Blueprint, g, render_template

from kampan import models
from kampan.web import acl

module = Blueprint("requests", __name__, url_prefix="/requests")

ANY_ORGANIZATION_ROLE = [role for role, _ in models.organizations.ORGANIZATION_ROLES]


@module.route("/")
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def index():
    return render_template("/snor_car/requests/index.html", organization=g.organization)
