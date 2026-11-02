from flask import Blueprint, redirect, url_for

from kampan.web import acl

module = Blueprint("details", __name__, url_prefix="/<organization_id>/details")


# รวมเข้าหน้าภาพรวมองค์กรแล้ว เก็บ URL เดิมไว้ให้ bookmark ยังใช้ได้
@module.route("/")
@acl.organization_roles_required("admin")
def index(organization_id):
    return redirect(
        url_for("organizations.overview.index", organization_id=organization_id),
        code=301,
    )
