from bson import ObjectId
from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    current_app,
    abort,
    flash,
    g,
)
from flask_login import current_user
from kampan.web import forms, acl
from kampan import models, utils
from flask_mongoengine import Pagination
import datetime
from .. import redis_rq

module = Blueprint("approve_orders", __name__, url_prefix="/approve_orders")

ALREADY_PROCESSED_MESSAGE = "รายการนี้ดำเนินการไปแล้ว"
INVALID_REQUEST_MESSAGE = "คำขอไม่ถูกต้อง กรุณาลองใหม่อีกครั้ง"
INSUFFICIENT_STOCK_MESSAGE = "จำนวนที่เลือกมากกว่าจำนวนวัสดุที่มี"


def get_order(organization, order_id):
    if not organization or not ObjectId.is_valid(order_id):
        abort(404)
    order = models.OrderItem.objects(id=order_id, organization=organization).first()
    if not order:
        abort(404)
    return order


def claim_order(order, expected_status: str, **updates) -> bool:
    """เปลี่ยนสถานะใบเบิกแบบ atomic เฉพาะเมื่อสถานะยังเป็น expected_status

    กดซ้ำ / กดพร้อมกัน / หน้าจอค้างข้อมูลเก่า: คนแรกได้ไป คนถัดไปได้ False
    """
    set_updates = {f"set__{key}": value for key, value in updates.items()}
    set_updates["set__updated_date"] = datetime.datetime.now()
    claimed = models.OrderItem.objects(
        id=order.id, organization=order.organization, status=expected_status
    ).update_one(**set_updates)
    return bool(claimed)


def get_checkout_pieces(checkout) -> int:
    return (checkout.set_ * checkout.item.piece_per_set) + checkout.piece


def take_from_inventories(item, quantity: int):
    """ตัดของจาก inventory ของ item แบบ atomic (ไม่ให้ remain ติดลบ)

    คืน list ของ (inventory, จำนวนที่ตัด) หรือ None ถ้าตัดได้ไม่ครบ
    (กรณีนี้จะคืนของที่ตัดไปแล้วกลับให้เอง)
    """
    taken = []
    remaining = quantity
    inventories = models.Inventory.objects(
        item=item, remain__gt=0, status="active"
    ).order_by("-remain")
    for inventory in inventories:
        if remaining <= 0:
            break
        amount = min(inventory.remain, remaining)
        updated = models.Inventory.objects(
            id=inventory.id, remain__gte=amount
        ).update_one(dec__remain=amount)
        if not updated:
            # มีคนตัดของก้อนนี้ไปพร้อมกัน ข้ามไปก้อนถัดไป
            continue
        taken.append((inventory, amount))
        remaining -= amount

    if remaining > 0:
        return_to_inventories(taken)
        return None
    return taken


def return_to_inventories(taken) -> None:
    for inventory, amount in taken:
        models.Inventory.objects(id=inventory.id).update_one(inc__remain=amount)


def get_next_ordinal_number(organization) -> str:
    """เลขลำดับใบเบิกที่อนุมัติแล้ว นับแยกตามหน่วยงาน (ต่อจากเลขสูงสุดของหน่วยงาน)"""
    numbers = [
        int(order.ordinal_number)
        for order in models.OrderItem.objects(
            organization=organization, ordinal_number__nin=[None, ""]
        ).only("ordinal_number")
        if str(order.ordinal_number).isdigit()
    ]
    return str(max(numbers, default=0) + 1)


def approve_order_by_admin(order):
    """อนุมัติใบเบิกและตัด stock คืนข้อความ error หรือ None ถ้าสำเร็จ"""
    checkouts = list(models.CheckoutItem.objects(order=order, status="active"))
    for checkout in checkouts:
        if get_checkout_pieces(checkout) > checkout.item.get_amount_pieces():
            return INSUFFICIENT_STOCK_MESSAGE

    approved_date = datetime.datetime.now()
    if not claim_order(
        order,
        "pending on admin",
        status="approved",
        approval_status="approved",
        approved_date=approved_date,
    ):
        return ALREADY_PROCESSED_MESSAGE

    taken_by_checkout = []
    for checkout in checkouts:
        taken = take_from_inventories(checkout.item, get_checkout_pieces(checkout))
        if taken is None:
            # stock ถูกตัดไปพร้อมกันระหว่างทาง: คืนของทั้งหมดและคืนสถานะใบเบิก
            for _, previous in taken_by_checkout:
                return_to_inventories(previous)
            models.OrderItem.objects(id=order.id, status="approved").update_one(
                set__status="pending on admin",
                set__approval_status="pending",
                unset__approved_date=True,
            )
            return INSUFFICIENT_STOCK_MESSAGE
        taken_by_checkout.append((checkout, taken))

    for checkout, taken in taken_by_checkout:
        checkout.status = "active"
        checkout.approval_status = "approved"
        checkout.inventories.extend(inventory for inventory, _ in taken)
        checkout.save()

    models.OrderItem.objects(id=order.id).update_one(
        set__ordinal_number=get_next_ordinal_number(order.organization)
    )
    return None


def deny_order(order_id, expected_status: str, denied_status: str, index_endpoint):
    order = get_order(g.organization, order_id)
    form = forms.approve_orders.OrderActionForm()
    index_url = url_for(index_endpoint, organization_id=g.organization.id)
    if not form.validate_on_submit():
        flash(INVALID_REQUEST_MESSAGE, "error")
        return redirect(index_url)

    if not claim_order(
        order,
        expected_status,
        status=denied_status,
        approval_status=denied_status,
        remark=form.reason.data or "",
    ):
        flash(ALREADY_PROCESSED_MESSAGE, "warning")
        return redirect(index_url)

    models.CheckoutItem.objects(order=order, status="active").update(
        set__status="denied"
    )
    return redirect(index_url)


@module.route("/item_checkouts", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser")
def item_checkouts():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    order_id = request.args.get("order_id")
    order = get_order(g.organization, order_id)
    checkouts = models.CheckoutItem.objects(order=order, status="active")
    page = request.args.get("page", default=1, type=int)
    paginated_checkouts = Pagination(checkouts, page=page, per_page=30)
    return render_template(
        "/approve_orders/item_checkouts.html",
        paginated_checkouts=paginated_checkouts,
        order_id=order_id,
        checkouts=checkouts,
        organization=organization,
    )


# ----------------- Endorser -----------------


@module.route("/endorser", methods=["GET", "POST"])
@acl.organization_roles_required("head", "endorser")
def endorser_index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    orders = models.OrderItem.objects(
        approval_status="pending",
        status="confirmed",
        organization=organization,
        head_endorser=current_user._get_current_object(),
    )

    form = forms.inventories.SearchStartEndDateForm()
    if form.start_date.data == None and form.end_date.data != None:
        orders = orders.filter(
            created_date__lt=form.end_date.data,
        )

    elif form.start_date.data and form.end_date.data == None:
        orders = orders.filter(
            created_date__gte=form.start_date.data,
        )

    elif form.start_date.data != None and form.end_date.data != None:
        orders = orders.filter(
            created_date__gte=form.start_date.data,
            created_date__lt=form.end_date.data,
        )
    page = request.args.get("page", default=1, type=int)
    if form.start_date.data:
        page = 1
    paginated_orders = Pagination(orders, page=page, per_page=100)
    return render_template(
        "/approve_orders/endorser/endorser_approve_index.html",
        paginated_orders=paginated_orders,
        form=form,
        orders=orders,
        organization=organization,
    )


@module.route("/<order_id>/endorser_approve", methods=["POST"])
@acl.organization_roles_required("head", "endorser")
def endorser_approve(order_id):
    order = get_order(g.organization, order_id)
    form = forms.approve_orders.OrderActionForm()
    index_url = url_for(
        "approve_orders.endorser_index", organization_id=g.organization.id
    )
    if not form.validate_on_submit():
        flash(INVALID_REQUEST_MESSAGE, "error")
        return redirect(index_url)

    if not claim_order(order, "confirmed", status="pending on supervisor supplier"):
        flash(ALREADY_PROCESSED_MESSAGE, "warning")
        return redirect(index_url)

    checkout_items = models.CheckoutItem.objects(order=order, status="active")
    for checkout in checkout_items:
        item = checkout.item
        if get_checkout_pieces(checkout) > item.get_amount_pieces():
            checkout.piece = item.get_amount_pieces()
            checkout.quantity = item.get_amount_pieces()
        checkout.save()

    order.reload()
    job = redis_rq.redis_queue.queue.enqueue(
        utils.email_utils.force_send_email_to_supervisor_supplier,
        args=(order, current_user._get_current_object(), current_app.config),
        job_id=f"force_sent_email_head_endorser_order_{order.id}",
        timeout=600,
        job_timeout=600,
    )
    print("=====> submit", job.get_id())
    return redirect(index_url)


@module.route("/<order_id>/endorser_denied", methods=["POST"])
@acl.organization_roles_required("head", "endorser")
def endorser_denied(order_id):
    return deny_order(order_id, "confirmed", "denied", "approve_orders.endorser_index")


@module.route("/<order_id>/endorser_approved_detail", methods=["GET", "POST"])
@acl.organization_roles_required("head", "endorser")
def endorser_approved_detail(order_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    order = get_order(g.organization, order_id)
    checkouts = models.CheckoutItem.objects(order=order, status="active")
    page = request.args.get("page", default=1, type=int)
    paginated_checkouts = Pagination(checkouts, page=page, per_page=100)
    return render_template(
        "/approve_orders/endorser/endorser_approve_detail.html",
        action_form=forms.approve_orders.OrderActionForm(),
        paginated_checkouts=paginated_checkouts,
        order_id=order_id,
        order=order,
        checkouts=checkouts,
        organization=organization,
    )


# ----------------- Supervisor Supplier -----------------


@module.route("/supervisor_supplier", methods=["GET", "POST"])
@acl.organization_roles_required("supervisor supplier")
def supervisor_supplier_index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    orders = models.OrderItem.objects(
        approval_status="pending",
        status="pending on supervisor supplier",
        organization=organization,
    )

    form = forms.inventories.SearchStartEndDateForm()
    if form.start_date.data == None and form.end_date.data != None:
        orders = orders.filter(
            created_date__lt=form.end_date.data,
        )

    elif form.start_date.data and form.end_date.data == None:
        orders = orders.filter(
            created_date__gte=form.start_date.data,
        )

    elif form.start_date.data != None and form.end_date.data != None:
        orders = orders.filter(
            created_date__gte=form.start_date.data,
            created_date__lt=form.end_date.data,
        )
    page = request.args.get("page", default=1, type=int)
    if form.start_date.data:
        page = 1
    paginated_orders = Pagination(orders, page=page, per_page=100)
    return render_template(
        "/approve_orders/supervisor_supplier/supervisor_supplier_approve_index.html",
        paginated_orders=paginated_orders,
        form=form,
        orders=orders,
        organization=organization,
    )


@module.route("/<order_id>/supervisor_supplier_approve", methods=["POST"])
@acl.organization_roles_required("supervisor supplier")
def supervisor_supplier_approve(order_id):
    order = get_order(g.organization, order_id)
    form = forms.approve_orders.OrderActionForm()
    index_url = url_for(
        "approve_orders.supervisor_supplier_index", organization_id=g.organization.id
    )
    if not form.validate_on_submit():
        flash(INVALID_REQUEST_MESSAGE, "error")
        return redirect(index_url)

    if not claim_order(
        order,
        "pending on supervisor supplier",
        status="pending on admin",
        remark=form.reason.data or "",
    ):
        flash(ALREADY_PROCESSED_MESSAGE, "warning")
        return redirect(index_url)

    order.reload()
    redis_rq.redis_queue.queue.enqueue(
        utils.email_utils.force_send_email_to_admin,
        args=(order, current_user._get_current_object(), current_app.config),
        job_id=f"force_sent_email_supervisor_supplier_order_{order.id}",
        timeout=600,
        job_timeout=600,
    )
    return redirect(index_url)


@module.route("/<order_id>/supervisor_supplier_denied", methods=["POST"])
@acl.organization_roles_required("supervisor supplier")
def supervisor_supplier_denied(order_id):
    return deny_order(
        order_id,
        "pending on supervisor supplier",
        "denied",
        "approve_orders.supervisor_supplier_index",
    )


@module.route(
    "/<order_id>/supervisor_supplier_approved_detail", methods=["GET", "POST"]
)
@acl.organization_roles_required("supervisor supplier")
def supervisor_supplier_approved_detail(order_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    order = get_order(g.organization, order_id)
    checkouts = models.CheckoutItem.objects(order=order, status="active")
    page = request.args.get("page", default=1, type=int)
    paginated_checkouts = Pagination(checkouts, page=page, per_page=100)
    return render_template(
        "/approve_orders/supervisor_supplier/supervisor_supplier_approve_detail.html",
        action_form=forms.approve_orders.OrderActionForm(),
        paginated_checkouts=paginated_checkouts,
        order_id=order_id,
        order=order,
        checkouts=checkouts,
        organization=organization,
    )


@module.route("/<order_id>/supervisor_supplier_approve_page", methods=["GET", "POST"])
@acl.organization_roles_required("supervisor supplier")
def supervisor_supplier_approve_page(order_id):
    form = forms.approve_orders.SupplierApproveForm()
    order = get_order(g.organization, order_id)
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()

    # form.admin_approver.choices = [
    #     (str(org_user.user.id), org_user.user.get_name())
    #     for org_user in organization.get_organization_users()
    #     if ("admin" in org_user.roles)
    # ]
    if not form.validate_on_submit():
        # if order.admin_approver:
        #     form.admin_approver.data = str(order.admin_approver.id)
        return render_template(
            "/approve_orders/supervisor_supplier/supervisor_supplier_approve_page.html",
            order_id=order_id,
            form=form,
            order=order,
            organization=organization,
        )
    # order.admin_approver = models.User.objects(id=form.admin_approver.data).first()
    order.save()
    job = redis_rq.redis_queue.queue.enqueue(
        utils.email_utils.force_send_email_to_admin,
        args=(order, current_user._get_current_object(), current_app.config),
        job_id=f"force_sent_email_supervisor_supplier_order_{order.id}",
        timeout=600,
        job_timeout=600,
    )
    print("=====> submit", job.get_id())
    return redirect(
        url_for(
            "approve_orders.supervisor_supplier_approved_detail",
            organization_id=organization_id,
            order_id=order_id,
        )
    )


# ----------------- Admin -----------------


@module.route("/admin", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def admin_index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    orders = models.OrderItem.objects(
        status__in=["pending on admin", "admin denied", "approved"],
        organization=organization,
    ).order_by("-created_date")

    form = forms.inventories.SearchStartEndDateForm()
    if form.start_date.data == None and form.end_date.data != None:
        orders = orders.filter(
            created_date__lt=form.end_date.data,
        )

    elif form.start_date.data and form.end_date.data == None:
        orders = orders.filter(
            created_date__gte=form.start_date.data,
        )

    elif form.start_date.data != None and form.end_date.data != None:
        orders = orders.filter(
            created_date__gte=form.start_date.data,
            created_date__lt=form.end_date.data,
        )
    page = request.args.get("page", default=1, type=int)
    if form.start_date.data:
        page = 1
    paginated_orders = Pagination(orders, page=page, per_page=100)
    return render_template(
        "/approve_orders/admin/admin_approve_index.html",
        paginated_orders=paginated_orders,
        form=form,
        orders=orders,
        organization=organization,
    )


@module.route("/<order_id>/admin_approve", methods=["POST"])
@acl.organization_roles_required("admin")
def admin_approve(order_id):
    order = get_order(g.organization, order_id)
    form = forms.approve_orders.OrderActionForm()
    index_url = url_for("approve_orders.admin_index", organization_id=g.organization.id)
    if not form.validate_on_submit():
        flash(INVALID_REQUEST_MESSAGE, "error")
        return redirect(index_url)

    error = approve_order_by_admin(order)
    if error == INSUFFICIENT_STOCK_MESSAGE:
        flash(error, "error")
        return redirect(
            url_for(
                "approve_orders.admin_approved_detail",
                organization_id=g.organization.id,
                order_id=order.id,
            )
        )
    if error:
        flash(error, "warning")
    return redirect(index_url)


@module.route("/<order_id>/admin_denied", methods=["POST"])
@acl.organization_roles_required("admin")
def admin_denied(order_id):
    return deny_order(
        order_id, "pending on admin", "admin denied", "approve_orders.admin_index"
    )


@module.route("/<order_id>/admin_approved_detail", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def admin_approved_detail(order_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    order = get_order(g.organization, order_id)
    checkouts = models.CheckoutItem.objects(order=order, status="active")
    page = request.args.get("page", default=1, type=int)
    paginated_checkouts = Pagination(checkouts, page=page, per_page=100)
    return render_template(
        "/approve_orders/admin/admin_approve_detail.html",
        action_form=forms.approve_orders.OrderActionForm(),
        paginated_checkouts=paginated_checkouts,
        order_id=order_id,
        order=order,
        checkouts=checkouts,
        organization=organization,
    )


@module.route("/<order_id>/admin_approve_page", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def admin_approve_page(order_id):
    form = forms.approve_orders.AdminApproveForm()
    order = get_order(g.organization, order_id)
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    if not form.validate_on_submit():
        return render_template(
            "/approve_orders/admin/admin_approve_page.html",
            order_id=order_id,
            form=form,
            order=order,
            organization=organization,
        )
    error = approve_order_by_admin(order)
    if error == INSUFFICIENT_STOCK_MESSAGE:
        flash(error, "error")
        return redirect(
            url_for(
                "approve_orders.admin_approved_detail",
                organization_id=g.organization.id,
                order_id=order.id,
            )
        )
    if error:
        flash(error, "warning")
        return redirect(
            url_for("approve_orders.admin_index", organization_id=g.organization.id)
        )

    models.OrderItem.objects(id=order.id).update_one(
        set__sent_item_date=form.sent_item_date.data
    )
    order.reload()
    job = redis_rq.redis_queue.queue.enqueue(
        utils.email_utils.force_send_email_to_staff,
        args=(order, current_user._get_current_object(), current_app.config),
        job_id=f"force_sent_email_staff_order_{order.id}",
        timeout=600,
        job_timeout=600,
    )
    print("=====> submit", job.get_id())
    return redirect(
        url_for("approve_orders.admin_index", organization_id=g.organization.id)
    )


@module.route(
    "/<order_id>/change_quantity/organization/<organization_id>", methods=["POST"]
)
@acl.organization_roles_required("supervisor supplier", "admin")
def change_quantity(order_id, organization_id):
    order = get_order(g.organization, order_id)
    form = forms.approve_orders.OrderActionForm()
    detail_url = url_for(
        "approve_orders.supervisor_supplier_approved_detail",
        organization_id=g.organization.id,
        order_id=order.id,
    )
    if not form.validate_on_submit():
        flash(INVALID_REQUEST_MESSAGE, "error")
        return redirect(detail_url)

    # แก้จำนวนได้เฉพาะตอนรอหัวหน้าเจ้าหน้าที่พัสดุอนุมัติ (ตรงกับปุ่มในหน้า)
    if order.status != "pending on supervisor supplier":
        flash(ALREADY_PROCESSED_MESSAGE, "warning")
        return redirect(detail_url)

    checkout_items = models.CheckoutItem.objects(order=order, status="active")
    for checkout in checkout_items:
        quantity = request.form.get(f"{checkout.id}", type=int)
        if quantity is None:
            continue
        quantity = max(quantity, 0)
        checkout.piece = quantity
        checkout.quantity = quantity
        checkout.save()

    return redirect(detail_url)
