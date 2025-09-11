from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    send_file,
    abort,
)
from flask_login import login_required, current_user
import mongoengine as me
from flask_mongoengine import Pagination
import datetime

from kampan.web import forms, acl
from kampan import models

module = Blueprint("tor_years", __name__, url_prefix="/tor_years")


@module.route("/")
@login_required
@acl.roles_required("admin")
def index():
    organization = current_user.user_setting.current_organization

    if current_user.has_roles(["admin"]):
        tor_years = models.ToRYear.objects(status="active")
    else:
        tor_years = models.ToRYear.objects(
            created_by=current_user._get_current_object(), status="active"
        )

    return render_template(
        "/procurement/tor_years/index.html",
        tor_years=tor_years,
        organization=organization,
    )


@module.route("/create", methods=["GET", "POST"], defaults=dict(tor_year_id=None))
@module.route("/<tor_year_id>/edit", methods=["GET", "POST"])
@login_required
@acl.roles_required("admin")
def create_or_edit(tor_year_id):
    form = forms.procurement.ToRYearForm()
    organization = current_user.user_setting.current_organization

    tor_year = None

    if tor_year_id:
        tor_year = models.ToRYear.objects(id=tor_year_id, status="active").first()
        if not tor_year:
            return redirect(
                url_for("procurement.tor_years.index", organization_id=organization.id)
            )
        form = forms.procurement.ToRYearForm(obj=tor_year)
    else:
        if request.method == "GET":
            form.year.data = str(datetime.datetime.today().year + 543 + 1)

    if not form.validate_on_submit():
        return render_template(
            "/procurement/tor_years/create-or-edit.html",
            form=form,
            organization=organization,
        )

    if not tor_year:
        tor_year = models.ToRYear(
            created_by=current_user._get_current_object(),
        )

    form.populate_obj(tor_year)

    tor_year.last_updated_by = current_user._get_current_object()
    tor_year.save()

    return redirect(
        url_for("procurement.tor_years.index", organization_id=organization.id)
    )


@module.route("/<tor_year_id>/copy", methods=["GET", "POST"])
@login_required
@acl.roles_required("admin")
def copy_tor_year(tor_year_id):
    organization = current_user.user_setting.current_organization
    # ดึง ToRYear ต้นฉบับ
    tor_year = models.ToRYear.objects(id=tor_year_id, status="active").first()
    if not tor_year:
        return redirect(
            url_for("procurement.tor_years.index", organization_id=organization.id)
        )

    # สร้างฟอร์มใหม่
    form = forms.procurement.ToRYearForm()
    existing_disactive_year = None

    if request.method == "GET":
        # กำหนดค่า default: ปี+1, วันเดือนเดิมแต่ปี+1
        try:
            old_year = int(tor_year.year)
        except Exception:
            old_year = datetime.datetime.today().year + 543
        new_year = str(old_year + 1)
        form.year.data = new_year

        # ตรวจสอบว่ามีปีที่จะสร้างใหม่อยู่ในสถานะ disactive หรือไม่
        existing_disactive_year = models.ToRYear.objects(
            year=new_year, status="disactive"
        ).first()

        # เปลี่ยนปีของ started_date และ ended_date
        if tor_year.started_date:
            form.started_date.data = tor_year.started_date.replace(
                year=tor_year.started_date.year + 1
            )
        if tor_year.ended_date:
            form.ended_date.data = tor_year.ended_date.replace(
                year=tor_year.ended_date.year + 1
            )

    if form.validate_on_submit():
        # ตรวจสอบอีกครั้งก่อนบันทึก
        try:
            new_year_value = form.year.data
            existing_disactive_year = models.ToRYear.objects(
                year=new_year_value, status="disactive"
            ).first()
        except:
            existing_disactive_year = None

        if existing_disactive_year:
            # ถ้ามีปีที่ถูก disactive อยู่แล้ว ให้ redirect กลับไปหน้าเดิมพร้อมข้อมูล
            return render_template(
                "/procurement/tor_years/copy_with_existing.html",
                form=form,
                organization=organization,
                existing_year=existing_disactive_year,
                source_tor_year=tor_year,
            )

        new_tor_year = models.ToRYear()
        form.populate_obj(new_tor_year)
        new_tor_year.created_by = current_user._get_current_object()
        new_tor_year.last_updated_by = current_user._get_current_object()
        new_tor_year.save()
        return redirect(
            url_for("procurement.tor_years.index", organization_id=organization.id)
        )

    return render_template(
        "/procurement/tor_years/create-or-edit.html",
        form=form,
        organization=organization,
        existing_disactive_year=existing_disactive_year,
    )


@module.route("/<existing_year_id>/restore", methods=["POST"])
@login_required
@acl.roles_required("admin")
def restore_tor_year(existing_year_id):
    organization = current_user.user_setting.current_organization
    existing_year = models.ToRYear.objects(
        id=existing_year_id, status="disactive"
    ).first()
    if existing_year:
        existing_year.status = "active"
        existing_year.last_updated_by = current_user._get_current_object()
        existing_year.save()
    return redirect(
        url_for("procurement.tor_years.index", organization_id=organization.id)
    )


@module.route("/<tor_year_id>/force_copy", methods=["POST"])
@login_required
@acl.roles_required("admin")
def force_copy_tor_year(tor_year_id):
    organization = current_user.user_setting.current_organization
    # ดึง ToRYear ต้นฉบับ
    tor_year = models.ToRYear.objects(id=tor_year_id, status="active").first()
    if not tor_year:
        return redirect(
            url_for("procurement.tor_years.index", organization_id=organization.id)
        )

    # กำหนดค่า default: ปี+1, วันเดือนเดิมแต่ปี+1
    try:
        old_year = int(tor_year.year)
    except Exception:
        old_year = datetime.datetime.today().year + 543
    new_year = str(old_year + 1)

    # ตรวจสอบว่ามีปีที่เป็น disactive อยู่หรือไม่
    existing_disactive_year = models.ToRYear.objects(
        year=new_year, status="disactive"
    ).first()

    if existing_disactive_year:
        # อัพเดทข้อมูลจากปีต้นฉบับ และเปลี่ยนสถานะเป็น active
        existing_disactive_year.started_date = (
            tor_year.started_date.replace(year=tor_year.started_date.year + 1)
            if tor_year.started_date
            else None
        )
        existing_disactive_year.ended_date = (
            tor_year.ended_date.replace(year=tor_year.ended_date.year + 1)
            if tor_year.ended_date
            else None
        )
        existing_disactive_year.status = "active"
        existing_disactive_year.last_updated_by = current_user._get_current_object()
        existing_disactive_year.save()
    else:
        # สร้าง ToRYear ใหม่
        new_tor_year = models.ToRYear()
        new_tor_year.year = new_year
        new_tor_year.started_date = (
            tor_year.started_date.replace(year=tor_year.started_date.year + 1)
            if tor_year.started_date
            else None
        )
        new_tor_year.ended_date = (
            tor_year.ended_date.replace(year=tor_year.ended_date.year + 1)
            if tor_year.ended_date
            else None
        )
        new_tor_year.created_by = current_user._get_current_object()
        new_tor_year.last_updated_by = current_user._get_current_object()
        new_tor_year.save()

    return redirect(
        url_for("procurement.tor_years.index", organization_id=organization.id)
    )


@module.route("/<tor_year_id>/delete")
@login_required
@acl.roles_required("admin")
def delete(tor_year_id):
    organization = current_user.user_setting.current_organization
    tor_year = models.ToRYear.objects(id=tor_year_id, status="active").first()
    if not tor_year:
        return redirect(
            url_for("procurement.tor_years.index", organization_id=organization.id)
        )

    if (
        current_user.user_setting
        and current_user.user_setting.tor_year
        and current_user.user_setting.tor_year.id == tor_year.id
    ):
        return redirect(
            url_for("procurement.tor_years.index", organization_id=organization.id)
        )

    tor_year.status = "disactive"
    tor_year.last_updated_by = current_user._get_current_object()
    tor_year.save()
    return redirect(
        url_for("procurement.tor_years.index", organization_id=organization.id)
    )


@module.route("/<tor_year_id>/set_default", methods=["POST"])
@login_required
@acl.roles_required("admin")
def set_default_tor_year(tor_year_id):
    organization = current_user.user_setting.current_organization
    user = current_user._get_current_object()
    tor_year = models.ToRYear.objects(id=tor_year_id, status="active").first()
    if not tor_year:
        return redirect(
            url_for("procurement.tor_years.index", organization_id=organization.id)
        )

    if not user.user_setting:
        user.user_setting = models.users.UserSetting(
            current_organization=models.Organization.objects(
                id=organization.id
            ).first(),
            tor_year=tor_year,
        )
    else:
        user.user_setting.tor_year = tor_year
    user.save()
    return redirect(
        url_for("procurement.tor_years.index", organization_id=organization.id)
    )
