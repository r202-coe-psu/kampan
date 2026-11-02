from flask import Blueprint, redirect, url_for

from kampan.web import acl

module = Blueprint("organizations", __name__, url_prefix="/organizations")


# ย้ายไปอยู่ในระบบจัดการองค์กรแล้ว เก็บ URL เดิมไว้ให้ bookmark ยังใช้ได้
@module.route("/")
@acl.roles_required("admin")
def index():
    return redirect(url_for("organizations.system_organizations.index"), code=301)
