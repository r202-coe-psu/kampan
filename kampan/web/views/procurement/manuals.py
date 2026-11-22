from flask import (
    Blueprint,
    g,
    render_template,
    abort,
)
from flask_login import login_required

from kampan.web import acl, feature_flags

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

    # คู่มือเก่าซ่อนไว้ด้วย flag ใช้คู่มือ MA ใหม่เป็นค่าตั้งต้น
    template = (
        "/procurement/requisitions/manual.html"
        if feature_flags.is_legacy_manual_enabled()
        else "/procurement/manuals/ma_manual.html"
    )
    return render_template(
        template,
        organization=organization,
    )

