from calendar import calendar
from crypt import methods
from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from kampan.web import forms, acl
from kampan import models
import mongoengine as me
from flask_mongoengine import Pagination

module = Blueprint("item_registers", __name__, url_prefix="/item_registers")


@module.route("/", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "staff")
def index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    item_registers = models.RegistrationItem.objects(
        status__ne="disactive", organization=organization
    ).order_by("-created_date")
    form = forms.item_orders.SearchStartEndDateForm()
    form.item.label = "สถานะ"
    form.item.choices += [("pending", "รอดำเนินการ"), ("active", "ยืนยัน")]
    if form.start_date.data == None and form.end_date.data != None:
        item_registers = item_registers.filter(
            created_date__lt=form.end_date.data,
        )

    elif form.start_date.data and form.end_date.data == None:
        item_registers = item_registers.filter(
            created_date__gte=form.start_date.data,
        )

    elif form.start_date.data != None and form.end_date.data != None:
        item_registers = item_registers.filter(
            created_date__gte=form.start_date.data,
            created_date__lt=form.end_date.data,
        )
    if form.item.data:
        item_registers = item_registers.filter(status=form.item.data)
    page = request.args.get("page", default=1, type=int)
    if form.start_date.data or form.end_date.data:
        page = 1

    paginated_item_registers = Pagination(item_registers, page=page, per_page=30)

    return render_template(
        "/item_registers/index.html",
        item_registers=item_registers,
        paginated_item_registers=paginated_item_registers,
        form=form,
        organization=organization,
    )


@module.route(
    "/register",
    methods=["GET", "POST"],
)
@acl.organization_roles_required("admin", "endorser", "staff")
def register():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    form = forms.item_registers.ItemRegisterationForm()
    form.supplier.choices = [
        (str(supplier.id), supplier.get_supplier_name())
        for supplier in models.Supplier.objects(status="active")
    ]
    item_register = models.RegistrationItem()

    if not form.validate_on_submit():

        return render_template(
            "/item_registers/register.html",
            form=form,
            organization=organization,
        )

    if form.bill_file.data:
        if item_register.bill:
            item_register.bill.replace(
                form.bill_file.data,
                filename=form.bill_file.data.filename,
                content_type=form.bill_file.data.content_type,
            )
        else:
            item_register.bill.put(
                form.bill_file.data,
                filename=form.bill_file.data.filename,
                content_type=form.bill_file.data.content_type,
            )

    item_register.created_by = current_user._get_current_object()
    form.populate_obj(item_register)
    item_register.supplier = models.Supplier.objects(id=form.supplier.data).first()
    item_register.status = "pending"
    item_register.organization = organization
    item_register.save()

    return redirect(
        url_for(
            "item_registers.index",
            organization_id=organization_id,
        )
    )


@module.route("/<item_register_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "staff")
def edit(item_register_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    item_register = models.RegistrationItem.objects().get(id=item_register_id)
    form = forms.item_registers.ItemRegisterationForm(obj=item_register)

    if not form.validate_on_submit():
        return render_template(
            "/item_registers/register.html",
            form=form,
            organization=organization,
        )

    if form.bill_file.data:
        if item_register.bill:
            item_register.bill.replace(
                form.bill_file.data,
                filename=form.bill_file.data.filename,
                content_type=form.bill_file.data.content_type,
            )
        else:
            item_register.bill.put(
                form.bill_file.data,
                filename=form.bill_file.data.filename,
                content_type=form.bill_file.data.content_type,
            )

    form.populate_obj(item_register)
    item_register.organization = organization
    item_register.save()

    return redirect(
        url_for(
            "item_registers.index",
            organization_id=organization_id,
        )
    )


@module.route("/<item_register_id>/delete")
@acl.organization_roles_required("admin", "endorser", "staff")
def confirm_item_register(item_register_id):
    organization_id = request.args.get("organization_id")
    item_register = models.RegistrationItem.objects().get(id=item_register_id)
    inventories = models.Inventory.objects(
        registration=item_register, status__ne="disactive"
    )
    if inventories:
        for inventory in inventories:
            inventory.status = "active"
            inventory.save()
        item_register.status = "active"
        item_register.save()
    return redirect(
        url_for(
            "inventories.bill_item",
            item_register_id=item_register.id,
            organization_id=organization_id,
        )
    )


@module.route("/<item_register_id>/delete")
@acl.organization_roles_required("admin", "endorser", "staff")
def delete(item_register_id):
    organization_id = request.args.get("organization_id")

    item_register = models.RegistrationItem.objects().get(id=item_register_id)
    item_register.status = "disactive"
    inventories = models.Inventory.objects(registration=item_register)
    for inventory in inventories:
        inventory.status = "disactive"
        inventory.save()
    item_register.save()

    return redirect(
        url_for(
            "item_registers.index",
            organization_id=organization_id,
        )
    )
