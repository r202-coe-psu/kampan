from flask import Blueprint, render_template, redirect, url_for
import datetime
from ... import acl
from . import procurement_files, mas

module = Blueprint("admin", __name__, url_prefix="/admin")


@module.route("/")
@acl.roles_required("admin")
def index():
    return redirect(url_for("admin.accounts.user_roles"))
