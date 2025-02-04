from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from .. import models

module = Blueprint("site", __name__)


@module.route("/")
def index():
    return render_template("sites/index.html")


@module.route("/select_system")
@login_required
def select_system():
    organization = None

    if not organization:
        organization_user_role = models.OrganizationUserRole.objects(
            user=current_user,
            status__ne="disactive",
        ).first()
        if organization_user_role:
            organization = organization_user_role.organization

    if not organization:
        organization = current_user.get_current_organization()
    if organization:
        return render_template("sites/select_system.html", organization=organization)

    if "admin" in current_user.roles:
        return redirect(url_for("admin.index"))

    return render_template(
        "/accounts/index.html",
        user=current_user,
        organization=organization,
    )
