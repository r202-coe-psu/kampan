import datetime
from decimal import Decimal  # เพิ่ม
from io import BytesIO

from bson import ObjectId
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    flash,
    request,
    send_file,
    url_for,
    g,
)
from flask_login import current_user, login_required
from flask_mongoengine import Pagination
from PyPDF2 import PdfMerger

from kampan import models, utils
from kampan.web import forms

from ... import redis_rq

module = Blueprint("requisitions", __name__, url_prefix="/requisitions")


def apply_expiration_date_filter(procurements, date_range):
    if not date_range:
        return procurements

    today = datetime.datetime.now().date()

    if date_range == "expired":
        return procurements.filter(end_date__lt=today)
    if date_range == "1_month":
        end_date = today + datetime.timedelta(days=30)
        return procurements.filter(end_date__gte=today, end_date__lte=end_date)
    elif date_range == "3_months":
        end_date = today + datetime.timedelta(days=90)
        return procurements.filter(end_date__gte=today, end_date__lte=end_date)
    elif date_range == "6_months":
        end_date = today + datetime.timedelta(days=180)
        return procurements.filter(end_date__gte=today, end_date__lte=end_date)
    elif date_range == "1_year":
        end_date = today + datetime.timedelta(days=365)
        return procurements.filter(end_date__gte=today, end_date__lte=end_date)
    elif date_range == "more_than_1_year":
        end_date = today + datetime.timedelta(days=365)
        return procurements.filter(end_date__gt=end_date)

    return procurements


def generate_next_requisition_code():
    now = datetime.datetime.now()
    buddhist_year = now.year + 543
    suffix = f"/{buddhist_year}"
    last = models.Requisition.objects(requisition_code__endswith=suffix).order_by("-requisition_code").first()
    if last and last.requisition_code:
        last_number = int(last.requisition_code.split("/")[0])
        next_number = last_number + 1
    else:
        next_number = 1
    return f"{next_number:04d}/{buddhist_year}"


@module.route("", methods=["GET", "POST"])
@login_required
def index():
    organization = g.organization
    form = forms.requisitions.RequisitionFilterForm(request.args)
    query = {}

    category = request.args.get("category", "")
    name = request.args.get("name", "")
    product_number = request.args.get("product_number", "")
    asset_code = request.args.get("asset_code", "")
    procurement_id = request.args.get("procurement_id", "")
    expiration_date_range = request.args.get("expiration_date_range", "3_months")

    if category:
        query["category"] = category
    if name:
        query["name__icontains"] = name
    if product_number:
        query["product_numbers__icontains"] = product_number
    if asset_code:
        query["asset_codes__icontains"] = asset_code
    if procurement_id:
        query["id__icontains"] = procurement_id
    query["organization"] = organization

    procurements = models.Procurement.objects(**query)
    procurements = apply_expiration_date_filter(procurements, expiration_date_range)

    # ถ้ากด redirect button มาจากหน้ารายการ MA ให้ดึงค่าต่างๆ มาแสดงในช่องค้นหา
    if procurement_id:
        procurement = procurements.filter(id=procurement_id).first()
        if procurement:
            category = procurement.category
            name = procurement.name
            asset_code = ", ".join(procurement.asset_codes) if procurement.asset_codes else ""
            product_number = ", ".join(procurement.product_numbers) if procurement.product_numbers else ""

    # ถ้าไม่ใช่ admin ให้เห็นเฉพาะที่ responsible_by เป็นตัวเอง
    org_user_role = models.OrganizationUserRole.objects(
        user=current_user._get_current_object(),
        organization=organization,
        status="active",
    ).first()
    if org_user_role and current_user.has_organization_roles("staff") and not current_user.has_organization_roles("admin"):
        procurements = procurements.filter(responsible_by=org_user_role)

    # Order by expiration date (earliest first)
    procurements = procurements.order_by("end_date")

    page = request.args.get("page", default=1, type=int)
    per_page = request.args.get("per_page", default=8, type=int)
    paginated_procurements = Pagination(procurements, page=page, per_page=per_page)
    category_choices = models.procurement.CATEGORY_CHOICES
    return render_template(
        "procurement/requisitions/index.html",
        procurements=paginated_procurements.items,
        can_change_renewal=renewal_permission_checker(organization),
        form=form,
        paginated_procurements=paginated_procurements,
        organization=organization,
        category_choices=category_choices,
        selected_category=category,
        selected_name=name,
        selected_product_number=product_number,
        selected_asset_code=asset_code,
        selected_expiration_date_range=expiration_date_range,
    )


PROCUREMENT_RENEWAL_FORBIDDEN_MESSAGE = "คุณไม่มีสิทธิ์ต่ออายุหรือไม่ต่ออายุ MA รายการนี้"


def renewal_permission_checker(organization):
    """สิทธิ์กดต่ออายุ / ไม่ต่ออายุ MA: admin ได้ทุกรายการในหน่วยงาน · staff ได้เฉพาะ MA ที่ตัวเองเป็นผู้รับผิดชอบ"""
    if current_user.has_organization_roles("admin", organization=organization):
        return lambda procurement: True
    if not current_user.has_organization_roles("staff", organization=organization):
        return lambda procurement: False

    member = models.OrganizationUserRole.objects(
        user=current_user._get_current_object(), organization=organization, status="active"
    ).first()
    if not member:
        return lambda procurement: False
    return lambda procurement: any(
        getattr(responsible, "id", None) == member.id for responsible in (procurement.responsible_by or [])
    )


PROCUREMENT_NOT_PENDING_MESSAGE = "รายการนี้ดำเนินการไปแล้ว หรือไม่ได้อยู่ในสถานะรอดำเนินการ"


def claim_pending_procurement(procurement, organization, new_status: str) -> bool:
    """เปลี่ยนสถานะ MA จาก pending แบบ atomic · คืน False ถ้าสถานะไม่ใช่ pending แล้ว (เช่นกดซ้ำ)"""
    return bool(
        models.Procurement.objects(id=procurement.id, organization=organization, status="pending").update_one(
            set__status=new_status,
            set__last_updated_by=current_user._get_current_object(),
            set__updated_date=datetime.datetime.now(),
        )
    )


@module.route("/<requisition_procurement_id>/non-renewal", methods=["POST"])
@login_required
def non_renewal_action(requisition_procurement_id):
    organization = g.organization
    if not organization:
        abort(404)

    procurement = models.Procurement.objects(id=requisition_procurement_id, organization=organization).first()
    if not procurement:
        abort(404)

    if not renewal_permission_checker(organization)(procurement):
        flash(PROCUREMENT_RENEWAL_FORBIDDEN_MESSAGE, "error")
        return redirect(url_for("procurement.requisitions.index", organization_id=organization.id))

    if not claim_pending_procurement(procurement, organization, "disactive"):
        flash(PROCUREMENT_NOT_PENDING_MESSAGE, "error")
    return redirect(url_for("procurement.requisitions.index", organization_id=organization.id))


@module.route("/non-renewal")
@login_required
def non_renewal():
    organization = g.organization
    category = request.args.get("category", "")
    query = {"status": "disactive", "organization": organization}
    procurements = models.Procurement.objects(**query)
    org_user_role = models.OrganizationUserRole.objects(
        user=current_user._get_current_object(),
        organization=organization,
        status="active",
    ).first()
    if org_user_role and current_user.has_organization_roles("staff") and not current_user.has_organization_roles("admin"):
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


@module.route("/<requisition_procurement_id>/renewal-requested", methods=["POST"])
@login_required
def renewal_requested_action(requisition_procurement_id):
    organization = g.organization
    if not organization:
        abort(404)

    procurement = models.Procurement.objects(id=requisition_procurement_id, organization=organization).first()
    if not procurement:
        abort(404)

    if not renewal_permission_checker(organization)(procurement):
        flash(PROCUREMENT_RENEWAL_FORBIDDEN_MESSAGE, "error")
        return redirect(url_for("procurement.requisitions.index", organization_id=organization.id))

    # จองการเปลี่ยนสถานะก่อนสร้างคำขอ กันกดซ้ำแล้วได้คำขอ 2 รายการ
    if not claim_pending_procurement(procurement, organization, "renewal-requested"):
        flash(PROCUREMENT_NOT_PENDING_MESSAGE, "error")
        return redirect(url_for("procurement.requisitions.index", organization_id=organization.id))

    # สร้างรหัส requisition_code ใหม่
    requisition_code = generate_next_requisition_code()
    # สร้าง Requisition ใหม่
    requisition = models.Requisition(
        requisition_code=requisition_code,
        purchaser=(procurement.responsible_by[0] if procurement.responsible_by else None),
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
        organization=organization,
    )
    try:
        requisition.save()
    except Exception:
        # สร้างคำขอไม่สำเร็จ คืนสถานะ MA ให้กดใหม่ได้
        models.Procurement.objects(id=procurement.id, status="renewal-requested").update_one(set__status="pending")
        raise

    return redirect(url_for("procurement.requisitions.index", organization_id=organization.id))


@module.route("/renewal_requested")
@login_required
def renewal_requested():
    organization = g.organization
    form = forms.requisitions.RenewalRequestedFilterForm(request.args)
    org_user_role = models.OrganizationUserRole.objects(
        user=current_user._get_current_object(),
        organization=organization,
        status="active",
    ).first()

    query = {}

    requisition_code = request.args.get("requisition_code", "")
    status = request.args.get("status", "")
    if requisition_code:
        query["requisition_code__icontains"] = requisition_code
    if status:
        if status == "wait_admin":
            query["status"] = "progress"
            query["approval_history__not__elemMatch"] = {"approver_role": "admin", "action": "approved"}
        elif status == "wait_manager":
            query["status"] = "progress"
            query["approval_history__elemMatch"] = {"approver_role": "admin", "action": "approved"}
            query["approval_history__not__elemMatch"] = {"approver_role": "manager", "action": "approved"}
        else:
            query["status"] = status

    category = request.args.get("category", "")
    query["organization"] = organization
    requisitions = models.Requisition.objects(**query)

    # Determine user role hierarchy
    # is_admin_or_head = current_user.has_organization_roles(
    #     "admin"
    # ) or current_user.has_organization_roles("head")
    is_admin = current_user.has_organization_roles("admin")
    is_head = current_user.has_organization_roles("head")
    is_manager = current_user.has_organization_roles("manager")
    is_staff = current_user.has_organization_roles("staff")

    # Apply filters based on role (lowest privilege first)
    manager_requisitions = None
    manager_submitted_requisitions = None
    head_pending_requisitions = None

    if is_staff and not (is_admin or is_manager or is_head):
        # Filter by purchaser.user matching current_user
        staff_requisitions = []
        for req in requisitions:
            if req.purchaser and req.purchaser.user and req.purchaser.user.id == current_user.id:
                staff_requisitions.append(req.id)
        requisitions = requisitions.filter(id__in=staff_requisitions)

    elif is_manager and not (is_admin or is_head):
        manager_requisitions = requisitions.filter(
            selected_manager__manager=org_user_role,
            approval_history__not__elemMatch={
                "approver_role": "manager",
            },
        )
        manager_submitted_requisitions = requisitions.filter(
            selected_manager__manager=org_user_role,
            approval_history__elemMatch={
                "approver_role": "manager",
            },
        )

    elif is_head and not (is_admin or is_manager):
        purchaser_ids = models.OrganizationUserRole.objects(division=org_user_role.division).only("id")
        requisitions = requisitions.filter(purchaser__in=purchaser_ids)

    elif is_manager and is_staff and is_head and is_admin:
        manager_requisitions = requisitions.filter(
            selected_manager__manager=org_user_role,
            approval_history__not__elemMatch={
                "approver_role": "manager",
            },
        )
        manager_submitted_requisitions = requisitions.filter(
            selected_manager__manager=org_user_role,
            approval_history__elemMatch={
                "approver_role": "manager",
            },
        )

    # Retrieve division-scoped pending requisitions for the head role
    if is_head and org_user_role and org_user_role.division:
        purchaser_ids = models.OrganizationUserRole.objects(division=org_user_role.division).only("id")
        # Enforce that all shown requisitions belong to the user's own division
        requisitions = requisitions.filter(purchaser__in=purchaser_ids)
        head_pending_requisitions = requisitions.filter(
            approval_history__not__elemMatch={
                "approver_role": "head",
            },
        )

    # Exclude pending/submitted lists from the bottom list to avoid duplicates
    excluded_ids = []
    if manager_requisitions:
        excluded_ids.extend([req.id for req in manager_requisitions])
    if head_pending_requisitions:
        excluded_ids.extend([req.id for req in head_pending_requisitions])
    
    if excluded_ids:
        requisitions = requisitions.filter(id__nin=excluded_ids)

    requisitions = requisitions.order_by("-requisition_code")
    # print(requisitions[1].purchaser.to_json(indent=2))
    mas_list = models.MAS.objects(organization=organization)

    # Pagination
    page = request.args.get("page", default=1, type=int)
    per_page = request.args.get("per_page", default=10, type=int)
    paginated_requisitions = Pagination(requisitions, page=page, per_page=per_page)

    paginated_manager_requisitions = None
    if manager_requisitions is not None:
        manager_page = request.args.get("manager_page", default=1, type=int)
        paginated_manager_requisitions = Pagination(manager_requisitions, page=manager_page, per_page=per_page)

    paginated_manager_submitted_requisitions = None
    if manager_submitted_requisitions is not None:
        manager_submitted_page = request.args.get("manager_submitted_page", default=1, type=int)
        paginated_manager_submitted_requisitions = Pagination(
            manager_submitted_requisitions, page=manager_submitted_page, per_page=per_page
        )

    paginated_head_pending_requisitions = None
    if head_pending_requisitions is not None:
        head_page = request.args.get("head_page", default=1, type=int)
        paginated_head_pending_requisitions = Pagination(
            head_pending_requisitions, page=head_page, per_page=per_page
        )

    return render_template(
        "procurement/requisitions/renewal_requested.html",
        requisitions=paginated_requisitions.items,
        paginated_requisitions=paginated_requisitions,
        manager_requisitions=(paginated_manager_requisitions.items if paginated_manager_requisitions else []),
        manager_submitted_requisitions=(
            paginated_manager_submitted_requisitions.items if paginated_manager_submitted_requisitions else []
        ),
        head_pending_requisitions=(paginated_head_pending_requisitions.items if paginated_head_pending_requisitions else []),
        paginated_head_pending_requisitions=paginated_head_pending_requisitions,
        form=form,
        paginated_manager_requisitions=paginated_manager_requisitions,
        paginated_manager_submitted_requisitions=paginated_manager_submitted_requisitions,
        organization=organization,
        selected_category=category,
        status_choices=models.requisitions.STATUS_CHOICES,
        mas_list=mas_list,
    )


@module.route("/<requisition_procurement_id>/document")
@login_required
def document(requisition_procurement_id):
    organization = g.organization
    requisition = models.Requisition.objects(id=requisition_procurement_id, organization=organization).first()
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
        organization=organization,
    )


@module.route("/create", methods=["GET", "POST"], defaults=dict(requisition_procurement_id=None))
@module.route("/<requisition_procurement_id>/edit", methods=["GET", "POST"])
@login_required
def create_or_edit(requisition_procurement_id):
    organization = g.organization
    # กรรมการและผู้ขอซื้อต้องเป็นสมาชิก active ของหน่วยงานที่กำลังดูอยู่เท่านั้น
    members = list(models.OrganizationUserRole.objects(organization=organization, status="active").order_by("-first_name"))
    members_by_id = {str(member.id): member for member in members}
    requisition = None

    if requisition_procurement_id:
        requisition = models.Requisition.objects(id=requisition_procurement_id, organization=organization).first()
        form = forms.requisitions.RequisitionForm(obj=requisition)
    else:
        form = forms.requisitions.RequisitionForm()

    if requisition and request.method == "GET":
        for committee, committee_form in zip(requisition.committees, form.committees):
            committee_form.member.data = str(committee.member.id)

    member_choices = [(str(member.id), member.display_fullname()) for member in members]
    for committee_form in form.committees:
        committee_form.member.choices = [("-", "เลือกกรรมการ")] + member_choices

    current_org_user_role = next(
        (member for member in members if str(getattr(member.user, "id", "")) == str(current_user.id)),
        None,
    )

    if current_org_user_role:
        current_purchaser_choice = (
            str(current_org_user_role.id),
            current_org_user_role.display_fullname(),
        )
        form.purchaser.choices = [current_purchaser_choice]
        form.purchaser.data = current_purchaser_choice[0]
    else:
        form.purchaser.choices = [("-", "ไม่พบข้อมูลผู้ขอซื้อ")]
        form.purchaser.data = "-"

    is_valid = form.validate_on_submit()
    if request.method == "POST" and not is_valid:
        print("Form errors:", form.errors)

    if not is_valid:
        return render_template(
            "/procurement/requisitions/create_or_edit.html",
            form=form,
            organization=organization,
        )

    if not requisition:
        requisition = models.Requisition(
            created_by=current_user._get_current_object(),
            organization=organization,
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
            member_obj = members_by_id.get(committee_form.member.data)
            if not member_obj:
                abort(400)
            committee = models.requisitions.Committees(
                member=member_obj,
                committee_type=committee_form.committee_type.data,
                committee_position=committee_form.committee_position.data,
            )
            requisition.committees.append(committee)

    tor_file = form.tor_document.data
    qt_files = form.qt_document.data
    # Populate other fields
    del form.committees
    del form.items
    del form.tor_document
    del form.qt_document
    # del form.fund
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
            requisition.tor_document.put(tor_file, filename=tor_file.filename, content_type=tor_file.content_type)

    # Handle qt_document (ใบเสนอราคา)
    if qt_files:
        qt_files.seek(0)
        if requisition.qt_document:
            requisition.qt_document.replace(
                qt_files,
                filename=qt_files.filename,
                content_type=qt_files.content_type,
            )
        else:
            requisition.qt_document.put(qt_files, filename=qt_files.filename, content_type=qt_files.content_type)
    # Convert SelectField id to document instance for ReferenceField
    if current_org_user_role:
        requisition.purchaser = current_org_user_role
    elif form.purchaser.data and form.purchaser.data != "-":
        requisition.purchaser = members_by_id.get(form.purchaser.data)

    requisition.last_updated_by = current_user._get_current_object()
    requisition.save()
    job = redis_rq.redis_queue.queue.enqueue(
        utils.send_emails_to_head.send_email_to_head,
        args=(
            requisition,
            organization.id,
            current_user.id,
            current_app.config,
            organization,
        ),
        timeout=600,
        job_timeout=600,
    )
    print("=====> Header email job submitted", job.get_id())
    return redirect(
        url_for(
            "procurement.requisitions.renewal_requested",
            organization_id=organization.id,
        )
    )


# รวมไฟล์ ToR และ QT เป็น PDF เดียวแล้วดาวน์โหลดทั้งหมด
@module.route("/<requisition_procurement_id>/download/all")
@login_required
def download(requisition_procurement_id):
    organization = g.organization
    document = models.Requisition.objects(id=requisition_procurement_id, organization=organization).first()
    pdf_streams = []

    # ToR
    if document and document.tor_document and getattr(document.tor_document, "filename", None):
        try:
            tor_bytes = BytesIO(document.tor_document.read())
            pdf_streams.append(tor_bytes)
        except Exception:
            pass

    # QT (ใบเสนอราคา)
    if document and document.qt_document:
        qt_docs = document.qt_document
        # รองรับทั้งลิสต์และ GridFSProxy
        if not isinstance(qt_docs, list):
            qt_docs = [qt_docs]
        for qt_file in qt_docs:
            if hasattr(qt_file, "filename") and str(qt_file.filename).lower().endswith(".pdf"):
                try:
                    qt_bytes = BytesIO(qt_file.read())
                    pdf_streams.append(qt_bytes)
                except Exception:
                    continue

    # ไม่มีไฟล์ PDF เลย
    if not pdf_streams:
        return abort(404)

    # รวม PDF
    merger = PdfMerger()
    for pdf in pdf_streams:
        try:
            pdf.seek(0)
            merger.append(pdf)
        except Exception:
            continue
    output = BytesIO()
    merger.write(output)
    merger.close()
    output.seek(0)

    filename = f"requisition_{requisition_procurement_id}_all.pdf"

    return send_file(output, download_name=filename, mimetype="application/pdf")


@module.route("/<requisition_id>/action", methods=["POST"])
@login_required
def requisition_action(requisition_id):
    approver_role = request.form.get("approver_role")
    action = request.form.get("action")
    reason = request.form.get("reason")
    fund_id = request.form.get("fund")  # fallback เดิม
    fund_ids = request.form.getlist("fund_ids")  # ใหม่: เลือกหลายแหล่งเงิน
    manager_id = request.form.get("manager")

    organization = g.organization
    if not organization:
        abort(404)

    requisition = models.Requisition.objects(id=requisition_id, organization=organization).first()
    member_obj = models.OrganizationUserRole.objects(
        user=current_user._get_current_object(),
        organization=organization,
        status__ne="disactive",
    ).first()
    if not member_obj or not requisition:
        abort(404)

    if approver_role not in models.requisitions.APPROVAL_STEPS or action not in models.requisitions.APPROVAL_ACTIONS:
        abort(400)

    renewal_requested_url = url_for(
        "procurement.requisitions.renewal_requested",
        organization_id=organization.id,
    )
    # ตรวจสิทธิ์ ลำดับขั้น และการกดซ้ำ ก่อนเขียนข้อมูลใด ๆ (กติกาเดียวกับที่ template ใช้ซ่อน/ปิดปุ่ม)
    approval_error = requisition.get_approval_error(approver_role, current_user._get_current_object())
    if approval_error:
        flash(approval_error, "error")
        return redirect(renewal_requested_url)

    manager_obj = None
    allocations = []
    if approver_role == "admin" and action == "approved":
        if manager_id:
            if ObjectId.is_valid(manager_id):
                manager_obj = models.OrganizationUserRole.objects(
                    id=manager_id,
                    organization=organization,
                    roles="manager",
                    status__ne="disactive",
                ).first()
            if not manager_obj:
                abort(400)

        # ตรวจการจัดสรรงบทั้งหมดก่อนจองขั้น เพื่อไม่ให้ขั้นค้างเป็น "อนุมัติแล้ว" ทั้งที่จัดสรรไม่สำเร็จ
        allocations, allocation_error = get_fund_allocations(organization, fund_id, fund_ids)
        if allocation_error:
            flash(allocation_error, "error")
            return redirect(renewal_requested_url)

    approval = models.requisitions.ApprovalHistory(
        approver=member_obj,
        approver_role=approver_role,
        action=action,
        reason=reason if action == "rejected" and reason else None,
        timestamp=datetime.datetime.now(),
        last_ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
        user_agent=request.headers.get("User-Agent"),
    )
    # จองขั้นนี้แบบ atomic ก่อนจัดสรรงบหรือส่งอีเมล กันกดซ้ำ/กดพร้อมกันแล้วตัดงบ MAS ซ้ำ
    claimed = models.Requisition.objects(
        id=requisition.id,
        approval_history__not__elemMatch={"approver_role": approver_role},
    ).update_one(push__approval_history=approval)
    if not claimed:
        flash("ขั้นนี้ดำเนินการแล้ว", "error")
        return redirect(renewal_requested_url)

    user = current_user._get_current_object()
    reservations = []
    reserved_mas = []
    try:
        # Admin อนุมัติ: จองงบ MAS แบบหลายแหล่งตามที่ตรวจไว้แล้ว
        if allocations:
            fund_list = []
            for mas, amount in allocations:
                reservation = models.Reservation(
                    requisition=requisition,
                    mas=mas,
                    amount=amount,
                    reserved_by=user,
                    organization=organization,
                )
                reservation.save()
                reservations.append(reservation)

                mas.reservable_amount -= amount
                mas.last_updated_by = user
                mas.editable = False
                mas.save()
                reserved_mas.append((mas, amount))

                fund_list.append(models.requisitions.Funds(mas=mas, amount=amount, reservation=reservation))
            requisition.fund = fund_list

        if approver_role == "admin" and action == "approved":
            fund_source = request.form.get("fund_source")
            if fund_source:
                requisition.fund_source = fund_source
            if manager_obj:
                requisition.selected_manager = models.requisitions.SelectedManager(
                    manager=manager_obj,
                    is_acting=request.form.get("Acting") == "True",
                )

        # ไม่แก้ requisition.approval_history ใน object เพื่อให้ save() ไม่เขียนทับ entry ที่ request อื่นเพิ่ง push
        history = list(requisition.approval_history or []) + [approval]
        approved_roles = {h.approver_role for h in history if h.action == "approved"}
        rejected_roles = {h.approver_role for h in history if h.action == "rejected"}

        if rejected_roles:
            requisition.status = "incomplete"
        elif set(models.requisitions.APPROVAL_STEPS).issubset(approved_roles):
            requisition.status = "complete"
        else:
            requisition.status = "progress"
        requisition.last_updated_by = user
        requisition.save()

        if requisition.status == "complete":
            models.RequisitionTimeline(
                requisition=requisition,
                purchaser=requisition.purchaser,
                progress=[
                    models.Progress(
                        progress_status="request_created",
                        created_by=user,
                        last_ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
                        user_agent=request.headers.get("User-Agent"),
                        timestamp=datetime.datetime.now(),
                    )
                ],
                note=None,
                status="active",
                updated_date=datetime.datetime.now(),
                last_updated_by=user,
                created_date=datetime.datetime.now(),
                created_by=user,
                organization=organization,
            ).save()
    except Exception:
        rollback_approval(requisition, approval, reservations, reserved_mas)
        raise

    requisition.reload()
    enqueue_approval_emails(requisition, approver_role, action, manager_obj, organization)
    return redirect(renewal_requested_url)


def get_fund_allocations(organization, fund_id, fund_ids):
    """อ่านยอดจัดสรรจาก form (key = fund_amounts[<mas_id>]) คืน ([(mas, amount)], error)"""
    input_amounts = {}
    for key, value in request.form.items(multi=True):
        if key.startswith("fund_amounts[") and key.endswith("]"):
            mas_id = key[len("fund_amounts[") : -1]
            try:
                amount = Decimal(str(value or "0")).quantize(Decimal("0.01"))
            except Exception:
                amount = Decimal("0.00")
            input_amounts[mas_id] = input_amounts.get(mas_id, Decimal("0.00")) + amount

    if not fund_ids and fund_id:
        fund_ids = [fund_id]  # fallback เดิม

    allocations = []
    for mas_id in dict.fromkeys(fund_ids or []):
        amount = input_amounts.get(mas_id, Decimal("0.00"))
        if amount <= 0 or not ObjectId.is_valid(mas_id):
            continue
        mas = models.MAS.objects(id=mas_id, organization=organization).first()
        if not mas:
            continue
        if amount > (mas.reservable_amount or Decimal("0")):
            return [], f"ยอดจัดสรรจาก {mas.mas_code} เกินยอดที่จองได้"
        allocations.append((mas, amount))
    return allocations, None


def rollback_approval(requisition, approval, reservations, reserved_mas):
    """คืนสภาพเมื่อบันทึกการอนุมัติไม่สำเร็จหลังจองขั้นแล้ว เพื่อให้ผู้ใช้กดใหม่ได้"""
    models.Requisition.objects(id=requisition.id).update_one(
        __raw__={"$pull": {"approval_history": {"_id": approval._id}}}
    )
    for reservation in reservations:
        reservation.delete()
    for mas, amount in reserved_mas:
        mas.reload()
        mas.reservable_amount += amount
        mas.save()


def enqueue_approval_emails(requisition, approver_role, action, manager_obj, organization):
    """ส่งอีเมลหลังบันทึกสำเร็จแล้ว ถ้า Redis มีปัญหาให้ log ไว้ ไม่ทำให้การอนุมัติที่บันทึกแล้วล้ม"""
    jobs = []
    if action == "rejected":
        jobs.append(utils.rejected_emails.send_email_rejected_to_user_admin_committee)
    elif approver_role in ("head", "manager"):
        jobs.append(utils.approved_emails.send_email_approve_to_user_admin_committee)

    for job_function in jobs:
        try:
            job = redis_rq.redis_queue.queue.enqueue(
                job_function,
                args=(requisition, current_user.id, current_app.config, organization, approver_role),
                timeout=600,
                job_timeout=600,
            )
            print("=====> email job submitted", job.get_id())
        except Exception:
            current_app.logger.exception("enqueue email failed for requisition %s", requisition.id)

    if manager_obj:
        try:
            redis_rq.redis_queue.queue.enqueue(
                utils.send_email_to_manager.send_email_to_manager,
                args=(requisition, current_app.config, manager_obj, organization),
                timeout=600,
                job_timeout=600,
            )
        except Exception:
            current_app.logger.exception("enqueue manager email failed for requisition %s", requisition.id)


