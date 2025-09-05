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
from flask_mongoengine import Pagination
from io import BytesIO
from kampan.web import forms, acl
from kampan import models

import datetime

module = Blueprint("requisitions", __name__, url_prefix="/requisitions")


@module.route("", methods=["GET", "POST"])
@login_required
@acl.organization_roles_required("admin")
def index():
    organization = current_user.user_setting.current_organization
    tor_year = getattr(current_user.user_setting, "tor_year", None)

    category = request.args.get("category", "")

    query = {}
    if tor_year:
        query["tor_year"] = tor_year
    if category:
        query["category"] = category

    # Filter only items expiring within 7 days and status pending
    procurements = models.Procurement.objects(**query, status="pending").order_by(
        "end_date"
    )

    page = request.args.get("page", default=1, type=int)
    per_page = request.args.get("per_page", default=8, type=int)
    paginated_procurements = Pagination(procurements, page=page, per_page=per_page)

    category_choices = models.procurement.CATEGORY_CHOICES
    return render_template(
        "procurement/requisitions/index.html",
        procurements=paginated_procurements.items,
        paginated_procurements=paginated_procurements,
        organization=organization,
        category_choices=category_choices,
        selected_category=category,
    )


@module.route("/<requisition_procurement_id>/non-renewal")
@acl.organization_roles_required("admin")
def non_renewal(requisition_procurement_id):
    organization = current_user.user_setting.current_organization
    procurement = models.Procurement.objects(id=requisition_procurement_id).first()

    if not procurement:
        return redirect(
            url_for("procurement.requisitions.index", organization_id=organization.id)
        )

    procurement.status = "disactive"
    procurement.last_updated_by = current_user._get_current_object()
    procurement.save()
    return redirect(
        url_for("procurement.requisitions.index", organization_id=organization.id)
    )


@module.route("/non-renewal")
@login_required
@acl.organization_roles_required("admin")
def list_non_renewal():
    organization = current_user.user_setting.current_organization
    category = request.args.get("category", "")

    query = {"status": "disactive"}
    tor_year = getattr(current_user.user_setting, "tor_year", None)
    if tor_year:
        query["tor_year"] = tor_year

    procurements = models.Procurement.objects(**query).order_by("-end_date")
    category_choices = models.procurement.CATEGORY_CHOICES

    return render_template(
        "procurement/requisitions/non_renewal.html",
        items=procurements,
        organization=organization,
        category_choices=category_choices,
        selected_category=category,
    )


@module.route("/<requisition_procurement_id>/renewal-requested")
@acl.organization_roles_required("admin")
def renewal_requested(requisition_procurement_id):
    organization = current_user.user_setting.current_organization
    procurement = models.Procurement.objects(id=requisition_procurement_id).first()

    if not procurement:
        return redirect(
            url_for("procurement.requisitions.index", organization_id=organization.id)
        )

    # สร้างรหัส requisition_code ใหม่
    now = datetime.datetime.now()
    buddhist_year = now.year + 543
    prefix = f"{buddhist_year}-"
    last = (
        models.Requisition.objects(requisition_code__startswith=prefix)
        .order_by("-requisition_code")
        .first()
    )
    if last and last.requisition_code:
        last_number = int(last.requisition_code.split("-")[1])
        next_number = last_number + 1
    else:
        next_number = 1
    requisition_code = f"{buddhist_year}-{next_number:04d}"

    # สร้าง Requisition ใหม่
    requisition = models.Requisition(
        requisition_code=requisition_code,
        purchaser=procurement.responsible_by[0] if procurement.responsible_by else None,
        phone=None,
        reason=f"Renewal requested for procurement {procurement.name}",
        start_date=procurement.end_date,
        items=[
            models.RequisitionItem(
                product_name=procurement.name,
                category=procurement.category,
                amount=procurement.amount,
                company=procurement.company,
                quantity=1,
            )
        ],
        fund=None,
        created_by=current_user._get_current_object(),
        last_updated_by=current_user._get_current_object(),
    )

    requisition.save()

    procurement.status = "renewal-requested"
    procurement.last_updated_by = current_user._get_current_object()
    procurement.save()
    return redirect(
        url_for("procurement.requisitions.index", organization_id=organization.id)
    )


@module.route("/renewal_requested")
@login_required
@acl.organization_roles_required("admin")
def list_renewal_requested():
    organization = current_user.user_setting.current_organization
    category = request.args.get("category", "")
    requisitions = models.Requisition.objects().order_by("requisition_code")

    return render_template(
        "procurement/requisitions/renewal_requested.html",
        requisitions=requisitions,
        organization=organization,
        selected_category=category,
    )


@module.route("/<requisition_procurement_id>/document")
@login_required
@acl.organization_roles_required("admin")
def document(requisition_procurement_id):
    requisition = models.Requisition.objects(id=requisition_procurement_id).first()
    if not requisition:
        abort(404)

    return render_template(
        "procurement/requisitions/document.html",
        requisitions=requisition,
        datetime=datetime,
    )


@module.route("/create", methods=["GET", "POST"])
@module.route("/<requisition_procurement_id>/edit", methods=["GET", "POST"])
@login_required
@acl.organization_roles_required("admin")
def create_or_edit(requisition_procurement_id=None):
    organization = current_user.user_setting.current_organization
    members = organization.get_organization_users()
    funds = models.MAS.objects()

    requisition = (
        models.Requisition.objects(id=requisition_procurement_id).first()
        if requisition_procurement_id
        else None
    )

    # Count submitted items for POST
    if request.method == "POST":
        item_keys = [
            key
            for key in request.form.keys()
            if key.startswith("items-") and key.endswith("-product_name")
        ]
        item_count = len(item_keys)
    elif requisition and requisition.items:
        item_count = len(requisition.items)
    else:
        item_count = 1

    # Clamp to the allowed range [1,4] to match model/form constraints
    if item_count < 1:
        item_count = 1
    if item_count > 4:
        item_count = 4

    form = forms.requisitions.RequisitionForm(obj=requisition)
    form.purchaser.queryset = members
    form.fund.queryset = funds
    form.items.min_entries = item_count

    now = datetime.datetime.now()
    buddhist_year = now.year + 543
    prefix = f"{buddhist_year}-"
    last = (
        models.Requisition.objects(requisition_code__startswith=prefix)
        .order_by("-requisition_code")
        .first()
    )
    if last and last.requisition_code:
        last_number = int(last.requisition_code.split("-")[1])
        next_number = last_number + 1
    else:
        next_number = 1

    if requisition:
        preview_code = requisition.requisition_code
    else:
        preview_code = f"{buddhist_year}-{next_number:04d}"

    if not form.validate_on_submit():
        print(form.errors)
        return render_template(
            "/procurement/requisitions/create_or_edit.html",
            form=form,
            organization=organization,
            preview_code=preview_code,
        )

    # If creating, instantiate new object, else update existing
    if not requisition:
        requisition = models.Requisition()
        requisition.created_by = current_user._get_current_object()

    requisition.last_updated_by = current_user._get_current_object()
    requisition.items = [
        models.RequisitionItem(
            product_name=item_form.product_name.data,
            quantity=item_form.quantity.data,
            category=item_form.category.data,
            amount=item_form.amount.data,
            company=item_form.company.data,
        )
        for item_form in form.items
    ]

    form.populate_obj(requisition)

    if form.tor_document.data:
        if requisition.tor_document:
            requisition.tor_document.replace(
                form.tor_document.data,
                filename=form.tor_document.data.filename,
                content_type=form.tor_document.data.content_type,
            )
        else:
            requisition.tor_document.put(
                form.tor_document.data,
                filename=form.tor_document.data.filename,
                content_type=form.tor_document.data.content_type,
            )

    requisition.save()
    return redirect(
        url_for(
            "procurement.requisitions.list_renewal_requested",
            organization_id=organization.id,
        )
    )
