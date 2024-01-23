from flask import Blueprint, render_template, redirect, url_for
import datetime
from ... import acl

module = Blueprint("admin", __name__, url_prefix="/admin")


@module.route("/")
@acl.roles_required("admin")
def index():
    return render_template(
        "/admin/dashboard/index-admin.html",
    )
