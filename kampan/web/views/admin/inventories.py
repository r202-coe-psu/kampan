from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    send_file,
    abort,
)
from flask_mongoengine import Pagination
from flask_login import login_required, current_user

from kampan.web import forms, acl
from kampan import models


module = Blueprint("inventories", __name__, url_prefix="/inventories")


@module.route("/", methods=["GET", "POST"])
@login_required
@acl.roles_required("admin")
def index():
    form = forms.inventories.SearchStartEndDateForm()
    inventories = models.Inventory.objects(status="active")
    items = models.Item.objects(status="active")
    form.item.choices = [
        (item.id, f"{item.barcode_id} ({item.name})") for item in items
    ]
    if form.start_date.data == None and form.end_date.data != None:
        inventories = inventories.filter(
            created_date__lt=form.end_date.data,
        )

    elif form.start_date.data and form.end_date.data == None:
        inventories = inventories.filter(
            created_date__gte=form.start_date.data,
        )

    elif form.start_date.data != None and form.end_date.data != None:
        inventories = inventories.filter(
            created_date__gte=form.start_date.data,
            created_date__lt=form.end_date.data,
        )
    if form.item.data != None:
        inventories = inventories.filter(item=form.item.data)
    page = request.args.get("page", default=1, type=int)
    if form.start_date.data or form.end_date.data:
        page = 1
    paginated_inventories = Pagination(inventories, page=page, per_page=30)
    return render_template(
        "/admin/inventories/index.html",
        inventories=inventories,
        paginated_inventories=paginated_inventories,
        form=form,
    )


@module.route("/register", methods=["GET", "POST"])
@login_required
@acl.roles_required("admin")
def register():
    form = forms.inventories.InventoryForm()
    item_register_id = request.args.get("item_register_id")
    item_register = models.RegistrationItem.objects.get(id=item_register_id)

    items = models.Item.objects(status="active")
    if item_register.get_item_in_bill():
        items = items.filter(id__nin=item_register.get_item_in_bill())

    if items:
        form.item.choices = [
            (item.id, f"{item.barcode_id} ({item.name})") for item in items
        ]
    if not form.validate_on_submit():
        return render_template(
            "/admin/inventories/register.html",
            form=form,
            item_register=item_register,
        )

    inventory = models.Inventory()
    form.populate_obj(inventory)
    inventory.item = models.Item.objects(id=form.item.data).first()
    inventory.user = current_user._get_current_object()
    inventory.notification_status = True
    inventory.registration = item_register
    inventory.remain = inventory.quantity
    inventory.save()

    return redirect(url_for("admin.item_registers.index"))


@module.route("/<inventory_id>/edit", methods=["GET", "POST"])
@login_required
@acl.roles_required("admin")
def edit(inventory_id):
    inventory = models.Inventory.objects().get(id=inventory_id)
    form = forms.inventories.InventoryForm(obj=inventory)
    item_register = inventory.registration

    items = models.Item.objects(status="active")
    if item_register.get_item_in_bill():
        items = items.filter(id__nin=item_register.get_item_in_bill())
        items = list(items)
        if inventory.item:
            items.append(models.Item.objects(id=inventory.item.id).first())
    if items:
        form.item.choices = [
            (item.id, f"{item.barcode_id} ({item.name})") for item in items
        ]
        form.item.process(
            formdata=form.item.choices,
            data=inventory.item.id,
        )

    if not form.validate_on_submit():
        return render_template(
            "/admin/inventories/register.html",
            item_register=item_register,
            form=form,
        )

    form.populate_obj(inventory)
    # if form.bill_file.data:
    #     if inventory.bill:
    #         inventory.bill.replace(
    #             form.bill_file.data,
    #             filename=form.bill_file.data.filename,
    #             content_type=form.bill_file.data.content_type,
    #         )
    #     else:
    #         inventory.bill.put(
    #             form.bill_file.data,
    #             filename=form.bill_file.data.filename,
    #             content_type=form.bill_file.data.content_type,
    #         )
    inventory.item = models.Item.objects(id=form.item.data).first()
    inventory.user = current_user._get_current_object()
    inventory.registration = item_register
    inventory.remain = inventory.quantity
    inventory.save()

    return redirect(
        url_for(
            "admin.inventories.bill_item", item_register_id=inventory.registration.id
        )
    )


@module.route("/<inventory_id>/delete")
@login_required
@acl.roles_required("admin")
def delete(inventory_id):
    inventory = models.Inventory.objects().get(id=inventory_id)
    inventory.status = "disactive"
    inventory.save()

    return redirect(
        url_for(
            "admin.inventories.bill_item", item_register_id=inventory.registration.id
        )
    )


@module.route("/all-item", methods=["GET", "POST"])
@login_required
@acl.roles_required("admin")
def bill_item():
    item_register_id = request.args.get("item_register_id")
    item_register = models.RegistrationItem.objects.get(id=item_register_id)
    inventories = models.Inventory.objects(registration=item_register)
    page = request.args.get("page", default=1, type=int)
    paginated_inventories = Pagination(inventories, page=page, per_page=30)
    return render_template(
        "/admin/inventories/bill-item.html",
        paginated_inventories=paginated_inventories,
        item_register=item_register,
    )


@module.route("/<inventory_id>/file")
@login_required
@acl.roles_required("admin")
def bill(inventory_id):
    inventory = models.Inventory.objects.get(id=inventory_id)
    registration_item = models.RegistrationItem.objects(
        id=inventory.registration.id
    ).first()
    if not registration_item.bill:
        return abort(404)

    response = send_file(
        registration_item.bill,
        download_name=registration_item.bill.filename,
        mimetype=registration_item.bill.content_type,
    )
    return response
