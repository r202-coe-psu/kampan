from uuid import uuid4
from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    flash,
    abort,
    send_file,
)
from flask_login import login_required, current_user
from flask_mongoengine import Pagination
from kampan.web import acl, forms, redis_rq
from kampan import models, utils

import mongoengine as me
import datetime

module = Blueprint("mas", __name__, url_prefix="/mas")


@module.route("/")
@login_required
@acl.organization_roles_required("admin")
def index():
    organization = current_user.user_setting.current_organization
    year = request.args.get("year")
    mas_code = request.args.get("mas_code")
    description = request.args.get("description")
    amount = request.args.get("amount")

    query = {}
    if year:
        query["year"] = year
    if mas_code:
        query["mas_code__icontains"] = mas_code
    if description:
        query["description__icontains"] = description
    if amount:
        query["amount"] = amount
    form = forms.mas.MASSearchForm(request.args)
    organization_id = request.args.get("organization_id")

    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()

    if form.year.data:
        query["year"] = form.year.data
    if form.mas_code.data:
        query["mas_code__icontains"] = form.mas_code.data
    if form.description.data:
        query["description__icontains"] = form.description.data
    if form.amount.data:
        query["amount"] = form.amount.data

    mas = models.MAS.objects(status="active", **query).order_by("created_date")

    page = request.args.get("page", default=1, type=int)
    paginated_mas = Pagination(mas, page=page, per_page=20)
    total_amount = sum(m.amount or 0 for m in mas)
    total_remaining = sum(m.remaining_amount or 0 for m in mas)
    total_reservable = sum(m.reservable_amount or 0 for m in mas)

    return render_template(
        "procurement/mas/index.html",
        organization=organization,
        organization_id=organization_id,
        mas=paginated_mas.items,
        paginated_mas=paginated_mas,
        total_amount=total_amount,
        total_remaining=total_remaining,
        total_reservable=total_reservable,
        form=form,
    )


@module.route("/create", methods=["GET", "POST"])
@module.route("/<mas_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def create_or_edit(mas_id=None):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()

    mas = models.MAS.objects(id=mas_id).first() if mas_id else None
    form = forms.mas.MASForm(obj=mas)

    if not form.validate_on_submit():
        print(form.errors)
        return render_template(
            "procurement/mas/create_or_edit.html",
            form=form,
            organization=organization,
            mas=mas,
        )

    if not mas:
        mas = models.MAS()
        mas.created_by = current_user._get_current_object()

    form.populate_obj(mas)
    mas.last_updated_by = current_user._get_current_object()
    mas.remaining_amount = mas.amount
    mas.reservable_amount = mas.remaining_amount or 0
    mas.save()

    return redirect(url_for("admin.mas.index", organization_id=organization.id))


@module.route("/<mas_id>/delete", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def delete(mas_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()

    mas = models.MAS.objects(id=mas_id).first()
    if mas:
        mas.status = "closed"
        mas.save()

    return redirect(url_for("admin.mas.index", organization_id=organization.id))


@module.route("/<mas_id>/reservation", methods=["GET"])
@login_required
@acl.organization_roles_required("admin")
def reservation(mas_id):
    organization = current_user.user_setting.current_organization
    form = forms.reservations.SearchReservationForm(request.args)

    query = {}

    # Requisition search (must fetch IDs because MongoDB doesn't support joins)
    if form.requisition_code.data:
        requisition_ids = models.Requisition.objects(
            requisition_code__icontains=form.requisition_code.data
        ).values_list("id")
        query["requisition__in"] = requisition_ids

    # Reserved by search (must fetch IDs because MongoDB doesn't support joins)
    if form.reserved_by.data:
        from mongoengine.queryset.visitor import Q

        user_ids = models.User.objects(
            Q(first_name__icontains=form.reserved_by.data)
            | Q(last_name__icontains=form.reserved_by.data)
        ).values_list("id")
        query["reserved_by__in"] = user_ids

    if form.reservation_status.data:
        query["reservation_status"] = form.reservation_status.data
    if form.reserved_date.data:
        # Match the date regardless of time
        start = datetime.datetime.combine(form.reserved_date.data, datetime.time.min)
        end = datetime.datetime.combine(form.reserved_date.data, datetime.time.max)
        query["reserved_date__gte"] = start
        query["reserved_date__lte"] = end
    if form.amount.data:
        query["amount"] = form.amount.data
    if form.actual_amount.data:
        query["actual_amount"] = form.actual_amount.data

    organization = models.Organization.objects(
        id=organization.id, status="active"
    ).first()

    mas = models.MAS.objects(id=mas_id).first()
    reservations = models.Reservation.objects(
        mas=mas, status="active", **query
    ).order_by("-reserved_date")
    page = request.args.get("page", default=1, type=int)
    paginated_reservations = Pagination(reservations, page=page, per_page=20)

    return render_template(
        "procurement/mas/reservation.html",
        organization=organization,
        mas=mas,
        reservations=paginated_reservations.items,
        paginated_reservations=paginated_reservations,
        form=form,
    )


@module.route("/export_mas_excel_modal", methods=["GET"])
@acl.organization_roles_required("admin")
def export_excel_modal():
    modal_id = uuid4()
    form = forms.mas.ExportMASExcelForm()
    organization_id = request.args.get("organization_id")
    exported_file = models.export_file.ExportFile.objects(
        created_by=current_user._get_current_object()
    ).first()

    return render_template(
        "procurement/components/export_excel_modal.html",
        modal_id=modal_id,
        exported_file=exported_file,
        organization_id=organization_id,
        form=form,
    )


@module.route("/export_excel")
@acl.organization_roles_required("admin")
def export_excel():
    organization_id = request.args.get("organization_id")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    job_id = redis_rq.redis_queue.queue.enqueue(
        utils.export_file.process_mas_export,
        args=(current_user._get_current_object(), start_date, end_date),
        timeout=3600,
        job_timeout=1200,
    )
    flash("ระบบกำลังสร้างไฟล์ส่งออกข้อมูลบุคคลากร กรุณารอสักครู่", "info")
    return redirect(url_for("admin.mas.index", organization_id=organization_id))


@module.route("/download_exported_excel/<export_id>")
@acl.organization_roles_required("admin")
def download_exported_file(export_id):
    export_mas_excel = models.ExportFile.objects.get(id=export_id)
    if not export_mas_excel or not export_mas_excel.file:
        flash("ไม่พบไฟล์ที่ส่งออก กรุณาทำการส่งออกข้อมูลใหม่", "error")
        return redirect(url_for("admin.mas.index"))

    return send_file(
        export_mas_excel.file,
        as_attachment=True,
        download_name=f"{export_mas_excel.file_name}",
    )
