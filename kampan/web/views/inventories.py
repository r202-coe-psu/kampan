import datetime
from calendar import calendar
from pyexpat import model
from tabnanny import check
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
from kampan import models, utils
from kampan.repositories.item_registers import RegisterItemRepository

module = Blueprint("inventories", __name__, url_prefix="/inventories")


@module.route("/", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "staff")
def index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    form = forms.inventories.SearchStartEndDateForm()
    inventories = models.Inventory.objects(
        status="active", organization=organization
    ).order_by("-created_date")
    items = models.Item.objects(status="active")
    form.item.choices = [("", "เลือกวัสดุ")] + [
        (str(item.id), f"{item.barcode_id} ({item.name})") for item in items
    ]
    form.categories.choices = [("", "หมวดหมู่ทั้งหมด")] + [
        (str(category.id), category.name)
        for category in models.Category.objects(
            organization=organization, status="active"
        )
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

    if form.item.data:
        inventories = inventories.filter(item=form.item.data)

    if form.categories.data:
        items = models.Item.objects(categories=form.categories.data)
        list_inventories = []
        for item in items:
            inventories_ = inventories.filter(item=item.id)
            list_inventories += inventories_
        inventories = set(list_inventories)
        inventories = list(inventories)

    page = request.args.get("page", default=1, type=int)
    if form.validate_on_submit():
        page = 1

    paginated_inventories = Pagination(inventories, page=page, per_page=30)
    return render_template(
        "/inventories/index.html",
        inventories=inventories,
        paginated_inventories=paginated_inventories,
        form=form,
        organization=organization,
    )


@module.route("/register", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "staff")
def register():
    organization_id = request.args.get("organization_id")
    item_register_id = request.args.get("item_register_id")

    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    form = RegisterItemRepository.get_inventory_form(
        organization_id=organization_id,
        item_register_id=item_register_id,
    )
    item_register = models.RegistrationItem.objects.get(id=item_register_id)

    if not form.validate_on_submit():

        return render_template(
            "/inventories/register.html",
            form=form,
            item_register=item_register,
            organization=organization,
        )

    inventory = models.Inventory()
    form.populate_obj(inventory)
    inventory.item = models.Item.objects(id=form.item.data).first()
    inventory.quantity = form.set_.data * inventory.item.piece_per_set
    inventory.warehouse = models.Warehouse.objects(id=form.warehouse.data).first()
    inventory.created_by = current_user._get_current_object()
    inventory.status = "pending"
    inventory.registration = item_register
    inventory.remain = inventory.quantity
    inventory.organization = organization
    inventory.save()

    return redirect(
        url_for(
            "inventories.bill_item",
            item_register_id=item_register_id,
            organization_id=organization_id,
        )
    )


@module.route("/<inventory_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "staff")
def edit(inventory_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    inventory = models.Inventory.objects().get(id=inventory_id)
    form = forms.inventories.InventoryForm(obj=inventory)
    form.warehouse.choices = [
        (str(warehouse.id), warehouse.name)
        for warehouse in models.Warehouse.objects(
            status="active", organization=organization
        )
    ]
    item_register = inventory.registration

    items = models.Item.objects(status="active")
    if item_register.get_item_in_bill():
        items = items.filter(id__nin=item_register.get_item_in_bill())
        items = list(items)
        if inventory.item:
            items.append(models.Item.objects(id=inventory.item.id).first())
    if items:
        form.item.choices = [(str(item.id), f"{item.name}") for item in items]
        form.item.process(
            formdata=form.item.choices,
            data=str(inventory.item.id),
        )

    if not form.validate_on_submit():
        if inventory:
            form.warehouse.data = str(inventory.warehouse.id)
        return render_template(
            "/inventories/register.html",
            item_register=item_register,
            form=form,
            organization=organization,
        )

    form.populate_obj(inventory)

    inventory.item = models.Item.objects(id=form.item.data).first()
    inventory.warehouse = models.Warehouse.objects(id=form.warehouse.data).first()
    inventory.quantity = form.set_.data * inventory.item.piece_per_set
    inventory.created_by = current_user._get_current_object()
    inventory.status = "pending"
    inventory.registration = item_register
    inventory.remain = inventory.quantity
    inventory.organization = organization
    inventory.save()

    return redirect(
        url_for(
            "inventories.bill_item",
            item_register_id=inventory.registration.id,
            organization_id=organization_id,
        )
    )


@module.route("/<inventory_id>/delete")
@acl.organization_roles_required("admin", "endorser", "staff")
def delete(inventory_id):
    organization_id = request.args.get("organization_id")

    inventory = models.Inventory.objects().get(id=inventory_id)
    inventory.status = "disactive"
    inventory.save()

    return redirect(
        url_for(
            "inventories.bill_item",
            item_register_id=inventory.registration.id,
            organization_id=organization_id,
        )
    )


@module.route("/all-item", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "staff")
def bill_item():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    item_register_id = request.args.get("item_register_id")
    item_register = models.RegistrationItem.objects.get(id=item_register_id)
    inventories = models.Inventory.objects(
        registration=item_register, status__ne="disactive", organization=organization
    )
    page = request.args.get("page", default=1, type=int)
    paginated_inventories = Pagination(inventories, page=page, per_page=30)
    return render_template(
        "/inventories/bill-item.html",
        paginated_inventories=paginated_inventories,
        item_register=item_register,
        organization=organization,
    )


@module.route("/<inventory_id>/file")
@acl.organization_roles_required("admin", "endorser", "staff")
def bill(inventory_id):
    inventory = models.Inventory.objects.get(id=inventory_id)
    registration_item = models.RegistrationItem.objects(
        id=inventory.registration.id, status__ne="disactive"
    ).first()
    if not registration_item.bill:
        return abort(404)

    response = send_file(
        registration_item.bill,
        download_name=registration_item.bill.filename,
        mimetype=registration_item.bill.content_type,
    )
    return response


@module.route("item_register/<item_register_id>/upload_file", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "staff")
def upload_file_inventory_info(item_register_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    form = forms.inventories.UploadInventoryFileForm()
    item_register = models.RegistrationItem.objects.get(id=item_register_id)

    upload_completed = False
    errors = request.args.getlist("errors")

    if not form.validate_on_submit():
        return render_template(
            "/inventories/upload_file.html",
            form=form,
            item_register=item_register,
            errors=errors,
            organization=organization,
            upload_completed=upload_completed,
        )
    inventory_engagement_file = None
    if form.upload_file.data:
        inventory_engagement_file = models.inventories.InventoryEngagementFile()
        if inventory_engagement_file.file:
            inventory_engagement_file.file.replace(
                form.upload_file.data,
                filename=form.upload_file.data.filename,
                content_type=form.upload_file.data.content_type,
            )
        else:
            inventory_engagement_file.file.put(
                form.upload_file.data,
                filename=form.upload_file.data.filename,
                content_type=form.upload_file.data.content_type,
            )
        inventory_engagement_file.created_by = current_user._get_current_object()
        inventory_engagement_file.organization = organization
        inventory_engagement_file.registration = item_register
        inventory_engagement_file.save()
    if inventory_engagement_file:
        errors = utils.inventories.validate_upload_inventory_engagement(
            inventory_engagement_file.file, organization
        )
        if errors:
            inventory_engagement_file.status = "failed"
            inventory_engagement_file.updated_date = datetime.datetime.now()
            inventory_engagement_file.save()
        else:
            utils.inventories.process_inventory_engagement(
                inventory_engagement_file, organization
            )
            upload_completed = True

    return render_template(
        "/inventories/upload_file.html",
        form=form,
        item_register=item_register,
        organization=organization,
        errors=errors,
        upload_completed=upload_completed,
    )


@module.route("/download_template_inventory_file")
@acl.organization_roles_required("admin", "endorser", "staff")
def download_template_inventory_file():
    response = utils.inventories.get_template_inventory_file()
    return response
