from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from flask_mongoengine import Pagination
import mongoengine as me

from kampan import models
from kampan.web import acl, forms

# ระบบส่วนกลาง: รายการองค์กรทั้งหมด เพิ่ม/แก้ไข/ลบองค์กร อยู่ที่ /organizations/
# ใช้ได้เฉพาะผู้ใช้ที่มี role admin ระดับระบบ (User.roles) ไม่ใช่ admin ขององค์กร
# ส่วนสมาชิกขององค์กรใช้หน้า /organizations/<id>/members/ ร่วมกับ admin ขององค์กร
module = Blueprint("system_organizations", __name__)


def get_target_organization(organization_id):
    try:
        organization = models.Organization.objects(
            id=organization_id, status="active"
        ).first()
    except me.ValidationError:
        organization = None
    if not organization:
        abort(404)
    return organization


def render_system_page(template, **context):
    # organization ใน template คือหน่วยงานที่ผู้ใช้กำลังดู ใช้ render sidebar
    # หน่วยงานที่กำลังจัดการในหน้านี้ส่งมาเป็น target_organization
    return render_template(
        f"/organizations/system/organizations/{template}",
        organization=current_user.get_viewing_organization(),
        **context,
    )


@module.route("/")
@acl.roles_required("admin")
def index():
    organizations = models.Organization.objects(status="active").order_by("name")
    keyword = request.args.get("q", default="").strip()[:128]
    if keyword:
        organizations = organizations.filter(
            me.Q(name__icontains=keyword) | me.Q(description__icontains=keyword)
        )
    page = max(request.args.get("page", default=1, type=int), 1)
    return render_system_page(
        "index.html",
        paginated_organizations=Pagination(organizations, page=page, per_page=30),
        keyword=keyword,
    )


@module.route("/new", methods=["GET", "POST"], defaults={"organization_id": None})
@module.route("/<organization_id>/edit", methods=["GET", "POST"])
@acl.roles_required("admin")
def create_or_edit(organization_id):
    target_organization = (
        get_target_organization(organization_id)
        if organization_id
        else models.Organization()
    )
    form = forms.organizations.OrganizationForm(obj=target_organization)

    if not form.validate_on_submit():
        return render_system_page(
            "create_or_edit.html",
            form=form,
            target_organization=target_organization if organization_id else None,
        )

    form.populate_obj(target_organization)
    if not organization_id:
        target_organization.created_by = current_user._get_current_object()
    target_organization.last_updated_by = current_user._get_current_object()
    target_organization.save()
    flash(
        f"เพิ่มองค์กร {target_organization.name} แล้ว"
        if not organization_id
        else f"บันทึกองค์กร {target_organization.name} แล้ว",
        "success",
    )
    return redirect(url_for("organizations.system_organizations.index"))


@module.route("/<organization_id>/delete", methods=["POST"])
@acl.roles_required("admin")
def delete(organization_id):
    target_organization = get_target_organization(organization_id)
    target_organization.status = "disactive"
    target_organization.save()
    flash(f"ลบองค์กร {target_organization.name} แล้ว", "success")
    return redirect(url_for("organizations.system_organizations.index"))
