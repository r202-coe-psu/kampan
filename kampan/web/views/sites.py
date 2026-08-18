from flask import Blueprint, render_template, redirect, url_for, request, abort, g
from flask_login import login_required, current_user
from .. import models

module = Blueprint("site", __name__)


@module.route("/switch_organization")
@login_required
def switch_organization():
    """สลับหน่วยงานที่กำลังดูจากแถบด้านบน

    จำหน่วยงานที่เลือกไว้ใน user_setting ด้วย เพื่อให้หน้าที่ไม่ได้ส่ง organization_id
    มาทาง URL (เช่นฝั่ง procurement) ใช้หน่วยงานเดียวกันตาม
    """
    organization_id = request.args.get("organization_id")
    try:
        organization = models.Organization.objects(
            id=organization_id, status="active"
        ).first()
    except Exception:
        organization = None

    if not organization:
        return abort(403)

    user = current_user._get_current_object()
    if not user.switch_organization(organization):
        return abort(403)

    next_url = request.args.get("next")
    # รับเฉพาะ path ภายในเว็บ กันการถูกพาไปเว็บอื่น
    if not next_url or not next_url.startswith("/") or next_url.startswith("//"):
        next_url = url_for("site.select_system", organization_id=organization.id)

    return redirect(next_url)


@module.route("/")
def index():
    return redirect(url_for("accounts.login"))


@module.route("/select_system")
@login_required
def select_system():
    # g.organization ถูกตรวจแล้วว่าผู้ใช้เป็นสมาชิกจริง (ดู acl.resolve_viewing_organization)
    if getattr(g, "organization_denied", False):
        return abort(403)

    organization = g.organization
    if organization:
        # ผู้ดูแลระบบระดับ global ดูได้ทุกหน่วยงานจึงไม่ต้องมีฝ่ายในหน่วยงานนั้น
        if "admin" not in current_user.roles and not current_user.get_current_division(
            organization
        ):
            return redirect(
                url_for(
                    "accounts.index",
                    organization_id=organization.id,
                    errors="กรุณาติดต่อผู้ดูแลระบบเพื่อตั้งค่าแผนก (Please contact the administrator to select a division.)",
                )
            )

        return render_template("sites/select_system.html", organization=organization)

    if "admin" in current_user.roles:
        return redirect(url_for("admin.index"))

    return render_template(
        "/accounts/index.html",
        user=current_user,
        organization=organization,
    )
