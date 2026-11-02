"""URL เดิมของระบบส่วนกลาง /organizations/system/... เก็บไว้ให้ bookmark ยังใช้ได้

ย้ายไปที่:
- รายการ/เพิ่ม/แก้ไของค์กร  -> /organizations/, /organizations/new, /organizations/<id>/edit
- ผู้ใช้ทั้งหมด             -> /users/
- รายละเอียด/สมาชิกขององค์กร -> หน้าภาพรวมและหน้าสมาชิกขององค์กร (/organizations/<id>/...)
"""

from flask import Blueprint, redirect, request, url_for

from kampan.web import acl

module = Blueprint("legacy_system", __name__, url_prefix="/system")


def moved(endpoint, **values):
    params = request.args.to_dict()
    params.update(values)
    return redirect(url_for(endpoint, **params), code=301)


@module.route("/organizations/")
@acl.roles_required("admin")
def organizations():
    return moved("organizations.system_organizations.index")


@module.route("/organizations/create")
@acl.roles_required("admin")
def create_organization():
    return moved("organizations.system_organizations.create_or_edit")


@module.route("/organizations/<organization_id>/edit")
@acl.roles_required("admin")
def edit_organization(organization_id):
    return moved("organizations.system_organizations.create_or_edit", organization_id=organization_id)


@module.route("/organizations/<organization_id>/detail")
@acl.roles_required("admin")
def organization_detail(organization_id):
    return moved("organizations.overview.index", organization_id=organization_id)


@module.route("/organizations/<organization_id>/users")
@acl.roles_required("admin")
def organization_members(organization_id):
    return moved("organizations.members.index", organization_id=organization_id)


@module.route("/organizations/<organization_id>/add-member")
@acl.roles_required("admin")
def organization_add_member(organization_id):
    return moved("organizations.members.add_member", organization_id=organization_id)


@module.route("/organizations/<organization_id>/users/<org_user_id>/edit-roles")
@acl.roles_required("admin")
def organization_member_edit_roles(organization_id, org_user_id):
    return moved(
        "organizations.members.edit_roles",
        organization_id=organization_id,
        org_user_id=org_user_id,
    )


@module.route("/users/")
@acl.roles_required("admin")
def users():
    return moved("users.index")


@module.route("/users/<user_id>/edit-roles")
@acl.roles_required("admin")
def user_edit_roles(user_id):
    return moved("users.edit_roles", user_id=user_id)
