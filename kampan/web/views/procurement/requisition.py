from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    send_file,
    abort,
    Response,
)
from flask_login import login_required, current_user
from flask_mongoengine import Pagination
from kampan.web import forms, acl
from kampan import models

import datetime


module = Blueprint("requisitions", __name__, url_prefix="/requisitions")


def generate_next_requisition_code():
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
    return f"{buddhist_year}-{next_number:04d}"


@module.route("", methods=["GET", "POST"])
@login_required
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
    procurements = models.Procurement.objects(**query, status="pending")
    # ถ้าไม่ใช่ admin ให้เห็นเฉพาะที่ responsible_by เป็นตัวเอง
    org_user_role = models.OrganizationUserRole.objects(
        user=current_user._get_current_object()
    ).first()
    if (
        org_user_role
        and "staff" in current_user.roles
        and "admin" not in current_user.roles
    ):
        procurements = procurements.filter(responsible_by=org_user_role)

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


@module.route("/non-renewal", defaults={"requisition_procurement_id": None})
@module.route("/<requisition_procurement_id>/non-renewal")
@login_required
def non_renewal(requisition_procurement_id):
    organization = current_user.user_setting.current_organization
    if requisition_procurement_id:
        procurement = models.Procurement.objects(id=requisition_procurement_id).first()
        if not procurement:
            return redirect(
                url_for(
                    "procurement.requisitions.index", organization_id=organization.id
                )
            )
        procurement.status = "disactive"
        procurement.last_updated_by = current_user._get_current_object()
        procurement.save()
        return redirect(
            url_for("procurement.requisitions.index", organization_id=organization.id)
        )
    else:
        category = request.args.get("category", "")
        query = {"status": "disactive"}
        tor_year = getattr(current_user.user_setting, "tor_year", None)
        if tor_year:
            query["tor_year"] = tor_year
        procurements = models.Procurement.objects(**query)
        org_user_role = models.OrganizationUserRole.objects(
            user=current_user._get_current_object()
        ).first()
        if (
            org_user_role
            and "staff" in current_user.roles
            and "admin" not in current_user.roles
        ):
            procurements = procurements.filter(responsible_by=org_user_role)
        procurements = procurements.order_by("-end_date")
        category_choices = models.procurement.CATEGORY_CHOICES
        return render_template(
            "procurement/requisitions/non_renewal.html",
            items=procurements,
            organization=organization,
            category_choices=category_choices,
            selected_category=category,
        )


@module.route("/renewal_requested", defaults={"requisition_procurement_id": None})
@module.route("/<requisition_procurement_id>/renewal-requested")
@login_required
def renewal_requested(requisition_procurement_id):
    organization = current_user.user_setting.current_organization
    if requisition_procurement_id:
        procurement = models.Procurement.objects(id=requisition_procurement_id).first()
        if not procurement:
            return redirect(
                url_for(
                    "procurement.requisitions.index", organization_id=organization.id
                )
            )
        # สร้างรหัส requisition_code ใหม่
        requisition_code = generate_next_requisition_code()
        # สร้าง Requisition ใหม่
        requisition = models.Requisition(
            requisition_code=requisition_code,
            purchaser=(
                procurement.responsible_by[0] if procurement.responsible_by else None
            ),
            phone=None,
            reason=f"Renewal requested for procurement {procurement.name}",
            start_date=procurement.end_date,
            items=[
                models.RequisitionItem(
                    product_name=procurement.name,
                    category=procurement.category,
                    amount=procurement.amount,
                    currency=None,
                    quantity=1,
                )
            ],
            # ensure at least one committee entry exists so model validation passes
            committees=None,
            type="MA",
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
    else:
        category = request.args.get("category", "")
        requisitions = models.Requisition.objects()
        if "staff" in current_user.roles:
            requisitions = requisitions.filter(
                created_by=current_user._get_current_object()
            )
        requisitions = requisitions.order_by("-requisition_code")
        mas_list = models.MAS.objects()
        return render_template(
            "procurement/requisitions/renewal_requested.html",
            requisitions=requisitions,
            organization=organization,
            selected_category=category,
            mas_list=mas_list,
        )


@module.route("/<requisition_procurement_id>/document")
@login_required
def document(requisition_procurement_id):
    requisition = models.Requisition.objects(id=requisition_procurement_id).first()
    if not requisition:
        abort(404)

    # แยก committee ตาม type
    committees_by_type = {
        "specification": [],
        "procurement": [],
        "inspection": [],
    }
    for committee in requisition.committees:
        if committee.committee_type in committees_by_type:
            committees_by_type[committee.committee_type].append(committee)

    return render_template(
        "procurement/requisitions/document.html",
        requisitions=requisition,
        specification_committees=committees_by_type["specification"],
        procurement_committees=committees_by_type["procurement"],
        inspection_committees=committees_by_type["inspection"],
        datetime=datetime,
    )


@module.route(
    "/create", methods=["GET", "POST"], defaults=dict(requisition_procurement_id=None)
)
@module.route("/<requisition_procurement_id>/edit", methods=["GET", "POST"])
@login_required
def create_or_edit(requisition_procurement_id):
    form = forms.requisitions.RequisitionForm()
    organization = current_user.user_setting.current_organization
    members = organization.get_organization_users()
    requisition = None

    if requisition_procurement_id:
        requisition = models.Requisition.objects(id=requisition_procurement_id).first()
        form = forms.requisitions.RequisitionForm(obj=requisition)
        if request.method == "GET":
            for committee, committee_form in zip(
                requisition.committees, form.committees
            ):
                committee_form.member.data = str(committee.member.id)

    member_choices = [(str(member.id), member.display_fullname()) for member in members]
    for committee_form in form.committees:
        committee_form.member.choices.extend(member_choices)

    filtered_member_user = [
        (str(member.id), member.display_fullname())
        for member in members
        if str(getattr(member.user, "id", "")) == str(current_user.id)
    ]
    form.purchaser.choices = filtered_member_user

    if not form.validate_on_submit():
        return render_template(
            "/procurement/requisitions/create_or_edit.html",
            form=form,
            organization=organization,
        )

    if not requisition:
        requisition = models.Requisition(
            created_by=current_user._get_current_object(),
        )

    # Create items from form
    requisition.items = [
        models.RequisitionItem(
            product_name=item_form.product_name.data,
            quantity=item_form.quantity.data,
            category=item_form.category.data,
            amount=item_form.amount.data,
            currency=item_form.currency.data,
        )
        for item_form in form.items
    ]

    # Create committees from form
    requisition.committees = []
    for committee_form in form.committees:
        if committee_form.member.data != "-":
            member_obj = models.OrganizationUserRole.objects(
                id=committee_form.member.data
            ).first()
            committee = models.requisitions.Committees(
                member=member_obj,
                committee_type=committee_form.committee_type.data,
                committee_position=committee_form.committee_position.data,
            )
            requisition.committees.append(committee)

    tor_file = form.tor_document.data
    # qt_files = form.qt_document.data
    # Populate other fields
    del form.committees
    del form.items
    del form.tor_document
    del form.qt_document
    del form.fund
    form.populate_obj(requisition)

    # Handle ToR file
    if tor_file:
        tor_file.seek(0)
        if requisition.tor_document:
            requisition.tor_document.replace(
                tor_file,
                filename=tor_file.filename,
                content_type=tor_file.content_type,
            )
        else:
            requisition.tor_document.put(
                tor_file, filename=tor_file.filename, content_type=tor_file.content_type
            )

    # Convert SelectField id to document instance for ReferenceField
    if form.purchaser.data and form.purchaser.data != "-":
        requisition.purchaser = models.OrganizationUserRole.objects(
            id=form.purchaser.data
        ).first()

    requisition.last_updated_by = current_user._get_current_object()
    requisition.save()
    return redirect(
        url_for(
            "procurement.requisitions.renewal_requested",
            organization_id=organization.id,
        )
    )


@module.route("/<requisition_procurement_id>/download/<filename>")
@login_required
def download(requisition_procurement_id, filename):
    document = models.Requisition.objects(id=requisition_procurement_id).first()

    if (
        not document
        or not document.tor_document
        or document.tor_document.filename != filename
    ):
        return abort(403)

    response = send_file(
        document.tor_document,
        download_name=document.tor_document.filename,
        mimetype=document.tor_document.content_type,
    )

    return response


@module.route("/<requisition_id>/action", methods=["POST"])
@login_required
@acl.roles_required("head", "admin", "supervisor support")
def requisition_action(requisition_id):
    approver_role = request.form.get("approver_role")
    action = request.form.get("action")  # 'approved' or 'rejected'
    fund_id = request.form.get("fund")
    requisition = models.Requisition.objects(id=requisition_id).first()
    organization = current_user.user_setting.current_organization
    members = organization.get_organization_users()
    member_obj = next(
        (
            member
            for member in members
            if str(getattr(member.user, "id", "")) == str(current_user.id)
        ),
        None,
    )
    if not member_obj or not requisition:
        abort(404)
        # If admin approves and fund is provided, set fund
    if approver_role == "admin" and action == "approved" and fund_id:
        mas_obj = models.MAS.objects(id=fund_id).first()
        if mas_obj:
            requisition.fund = mas_obj

    approval = models.requisitions.ApprovalHistory(
        approver=member_obj,
        approver_role=approver_role,
        action=action,
        timestamp=datetime.datetime.now(),
    )
    if requisition.approval_history is None:
        requisition.approval_history = []
    requisition.approval_history.append(approval)
    requisition.status = action
    requisition.last_updated_by = current_user._get_current_object()
    requisition.save()
    return redirect(
        url_for(
            "procurement.requisitions.renewal_requested",
            organization_id=current_user.user_setting.current_organization.id,
        )
    )
