from atexit import register
from calendar import calendar
from pyexpat import model
from typing import OrderedDict
from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from flask_mongoengine import Pagination
from kampan.web import forms, acl
from kampan import models, utils
import mongoengine as me
import datetime

# สร้าง Blueprint สำหรับจัดการการเบิกพัสดุ
module = Blueprint("item_checkouts", __name__, url_prefix="/item_checkouts")


@module.route("/", methods=["GET", "POST"])
@acl.organization_roles_required(
    "admin", "endorser", "staff", "head", "supervisor supplier"
)
def index():
    """
    หน้าแสดงรายการเบิกพัสดุทั้งหมด
    - ผู้ใช้ทั่วไปจะเห็นเฉพาะรายการเบิกของตนเอง
    - admin และ supervisor supplier จะเห็นทุกรายการ
    - สามารถค้นหาและกรองข้อมูลตามวันที่, วัสดุ, และหมวดหมู่ได้
    """
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()

    # ตรวจสอบสิทธิ์ผู้ใช้เพื่อแสดงผลรายการเบิก
    if current_user.has_organization_roles("admin", "supervisor supplier"):
        # Admin และ Supervisor เห็นทุกรายการเบิกที่ active
        checkout_items = models.CheckoutItem.objects(
            status="active", organization=organization
        ).order_by("-created_date")
    else:
        # ผู้ใช้ทั่วไปเห็นเฉพาะรายการเบิกของตนเอง
        checkout_items = models.CheckoutItem.objects(
            status="active", organization=organization, user=current_user
        ).order_by("-created_date")

    # เตรียมฟอร์มสำหรับค้นหา
    items = models.Item.objects(status="active")
    form = forms.inventories.SearchStartEndDateForm()
    form.item.choices = [("", "เลือกวัสดุ")] + [
        (str(item.id), f"{item.barcode_id} ({item.name})") for item in items
    ]

    form.categories.choices = [("", "หมวดหมู่ทั้งหมด")] + [
        (str(category.id), category.name)
        for category in models.Category.objects(
            organization=organization, status="active"
        )
    ]

    # กรองข้อมูลตามวันที่ที่ระบุในฟอร์ม
    if form.start_date.data == None and form.end_date.data != None:
        checkout_items = checkout_items.filter(
            created_date__lt=form.end_date.data,
        )
    elif form.start_date.data and form.end_date.data == None:
        checkout_items = checkout_items.filter(
            created_date__gte=form.start_date.data,
        )
    elif form.start_date.data != None and form.end_date.data != None:
        checkout_items = checkout_items.filter(
            created_date__gte=form.start_date.data,
            created_date__lt=form.end_date.data,
        )
    
    # กรองข้อมูลตามวัสดุที่เลือก
    if form.item.data:
        checkout_items = checkout_items.filter(item=form.item.data)

    # กรองข้อมูลตามหมวดหมู่ที่เลือก
    if form.categories.data:
        items = models.Item.objects(categories=form.categories.data)
        list_checkout_items = []
        for item in items:
            checkout_items_ = checkout_items.filter(item=item.id)
            list_checkout_items += checkout_items_
        checkout_items = set(list_checkout_items)

    # จัดเรียงข้อมูลและทำ Pagination
    checkouts = list(checkout_items)
    checkouts = sorted(checkouts, key=lambda k: k["created_date"], reverse=True)

    page = request.args.get("page", default=1, type=int)
    if form.start_date.data or form.end_date.data:
        page = 1

    paginated_checkouts = Pagination(checkouts, page=page, per_page=30)
    return render_template(
        "/item_checkouts/index.html",
        checkouts=checkouts,
        form=form,
        paginated_checkouts=paginated_checkouts,
        organization=organization,
    )


@module.route("/order/<order_id>/catalogs", methods=["GET", "POST"])
@acl.organization_roles_required(
    "admin", "endorser", "staff", "head", "supervisor supplier"
)
def catalogs(order_id):
    """
    หน้าแคตตาล็อกสินค้าสำหรับเพิ่มรายการในใบเบิก
    - แสดงรายการสินค้าทั้งหมดที่สามารถเบิกได้
    - สามารถค้นหาสินค้าตามชื่อและหมวดหมู่
    """
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    order = models.OrderItem.objects(id=order_id).first()
    form = forms.items.SearcCategoryForm()

    items = models.Item.objects(
        status__in=["active"], organization=organization
    ).order_by("status", "-created_date")

    form.categories.choices = [("", "หมวดหมู่ทั้งหมด")] + [
        (str(category.id), category.name)
        for category in models.Category.objects(
            organization=organization, status="active"
        )
    ]

    if not form.validate_on_submit():
        # หากไม่ใช่การ submit form (เป็นการเข้าหน้าเว็บปกติหรือการค้นหาผ่าน GET)
        item_name = request.args.get("item_name")
        if item_name:
            form.item_name.data = item_name
            items = items.filter(name__icontains=form.item_name.data)

        categories = request.args.get("categories")
        if categories:
            form.categories.data = categories
            items = items.filter(categories=form.categories.data)

        # กรองเฉพาะสินค้าที่มีจำนวนคงเหลือมากกว่า 0
        list_items = []
        for item in items:
            if item.get_amount_pieces() > 0:
                list_items.append(item)
        items = list_items
        
        # จัดการ Pagination
        page = request.args.get("page", default=1, type=int)
        try:
            paginated_items = Pagination(items, page=page, per_page=24)
        except:
            paginated_items = Pagination(items, page=1, per_page=24)
            
        return render_template(
            "/item_checkouts/catalogs.html",
            paginated_items=paginated_items,
            items=items,
            form=form,
            organization=organization,
            order=order,
        )

    # หากเป็นการ submit form ให้ redirect พร้อม query string สำหรับการกรอง
    item_name = form.item_name.data
    categories = form.categories.data
    organization_id = organization.id
    return redirect(
        url_for(
            "item_checkouts.catalogs",
            organization_id=organization_id,
            item_name=item_name,
            categories=categories,
            order_id=order_id,
        )
    )


@module.route("/checkout", methods=["GET", "POST"])
@acl.organization_roles_required(
    "admin", "endorser", "staff", "head", "supervisor supplier"
)
def checkout():
    """
    หน้าสำหรับสร้างรายการเบิกสินค้า (CheckoutItem) ใหม่ในใบเบิก (OrderItem)
    - ถ้าสินค้านี้มีอยู่ในใบเบิกแล้ว จะ redirect ไปหน้าแก้ไข
    - แสดงฟอร์มสำหรับกรอกจำนวนที่ต้องการเบิก
    """
    organization_id = request.args.get("organization_id")
    item_id = request.args.get("item_id")

    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    form = forms.item_checkouts.CheckoutItemForm()
    order = models.OrderItem.objects(id=request.args.get("order_id")).first()
    
    # ตรวจสอบว่าสินค้านี้ถูกเบิกในใบเบิกนี้แล้วหรือยัง
    checkout_item = None
    if order and item_id:
        checkout_item = models.CheckoutItem.objects(
            item=item_id, order=order, status__ne="disactive"
        ).first()
    
    # ถ้ามีแล้ว ให้ไปหน้าแก้ไข
    if checkout_item:
        return redirect(
            url_for(
                "item_checkouts.edit",
                checkout_item_id=checkout_item.id,
                order_id=checkout_item.order.id,
                organization_id=organization_id,
            )
        )
        
    # เตรียมข้อมูลสำหรับฟอร์ม
    items = models.Item.objects(status="active")
    # ไม่แสดงสินค้าที่อยู่ในใบเบิกนี้แล้ว
    if order.get_item_in_bill():
        items = items.filter(id__nin=order.get_item_in_bill())

    if items:
        form.item.choices = [
            (
                str(item.id),
                (
                    f"{item.barcode_id} {item.name} (มีวัสดุทั้งหมด {item.get_items_quantity()})"
                    + (
                        f" ({item.set_unit} {item.piece_unit}ละ {item.piece_per_set})"
                        if item.piece_per_set > 1
                        else f" ({item.set_unit}ละ 1)"
                    )
                    + (
                        f" (จองอยู่ทั้งหมด {item.get_booking_item()})"
                        if item.get_booking_item() != 0
                        else ""
                    )
                    + (f" หมายเหตุ {item.remark}" if item.remark else "")
                ),
            )
            for item in items
        ]
        
    if not form.validate_on_submit():
        if item_id:
            form.item.data = str(item_id)
        return render_template(
            "/item_checkouts/checkout.html",
            form=form,
            order=order,
            organization=organization,
        )

    # บันทึกข้อมูลการเบิกใหม่
    item = models.Item.objects(id=form.item.data).first()
    checkout_item = models.CheckoutItem()
    checkout_item.user = current_user._get_current_object()
    checkout_item.order = order
    checkout_item.item = item
    checkout_item.created_date = form.created_date.data
    checkout_item.piece = form.piece.data
    checkout_item.quantity = form.piece.data # 'quantity' อาจจะซ้ำซ้อนกับ 'piece'
    checkout_item.organization = organization
    checkout_item.save()

    return render_template(
        "/item_checkouts/checkout.html",
        form=form,
        order=order,
        organization=organization,
        success=True,
    )


@module.route("/all-checkout", methods=["GET", "POST"])
@acl.organization_roles_required(
    "admin", "endorser", "staff", "head", "supervisor supplier"
)
def bill_checkout():
    """
    หน้าแสดงรายการสินค้าทั้งหมดในใบเบิก (บิล)
    """
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    order_id = request.args.get("order_id")
    order = models.OrderItem.objects.get(id=order_id)
    checkouts = models.CheckoutItem.objects(order=order, status__ne="disactive")

    # จัดการ Pagination
    page = request.args.get("page", default=1, type=int)
    paginated_checkouts = Pagination(checkouts, page=page, per_page=30)

    return render_template(
        "/item_checkouts/bill-checkout.html",
        paginated_checkouts=paginated_checkouts,
        order_id=order_id,
        checkouts=checkouts,
        organization=organization,
        order=order,
    )


@module.route("/checkout/<checkout_item_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required(
    "admin", "endorser", "staff", "head", "supervisor supplier"
)
def edit(checkout_item_id):
    """
    หน้าสำหรับแก้ไขรายการเบิกสินค้า (CheckoutItem) ที่มีอยู่แล้ว
    """
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    checkout_item = models.CheckoutItem.objects(id=checkout_item_id).first()
    order = models.OrderItem.objects(id=checkout_item.order.id).first()

    form = forms.item_checkouts.CheckoutItemForm(obj=checkout_item)
    
    # เตรียมข้อมูล Dropdown รายการสินค้า
    items = models.Item.objects(status="active")
    if order.get_item_in_bill():
        # กรองสินค้าที่อยู่ในบิลนี้แล้วออก แต่ยังคงแสดงสินค้าตัวที่กำลังแก้ไขอยู่
        items = items.filter(id__nin=order.get_item_in_bill())
        items = list(items)
        if checkout_item.item:
            items.append(models.Item.objects(id=checkout_item.item.id).first())
            
    if items:
        form.item.choices = [
            (
                str(item.id),
                (
                    f"{item.barcode_id} ({item.name}) (มีวัสดุทั้งหมด {item.get_items_quantity()})"
                    + (
                        f" ({item.set_unit} {item.piece_unit}ละ {item.piece_per_set})"
                        if item.piece_per_set > 1
                        else f" ({item.set_unit}ละ 1)"
                    )
                    + (
                        f" (จองอยู่ทั้งหมด {item.get_booking_item()})"
                        if item.get_booking_item() != 0
                        else ""
                    )
                ),
            )
            for item in items
        ]
        # ตั้งค่า default value สำหรับ dropdown
        form.item.process(data=checkout_item.item.id, formdata=form.item.choices)
        
    if not form.validate_on_submit():
        return render_template(
            "/item_checkouts/checkout.html",
            form=form,
            organization=organization,
            order=order,
        )
        
    # บันทึกข้อมูลที่แก้ไข
    item = models.Item.objects(id=form.item.data).first()
    checkout_item.user = current_user._get_current_object()
    checkout_item.item = item
    checkout_item.created_date = form.created_date.data
    checkout_item.quantity = form.piece.data
    checkout_item.piece = form.piece.data
    checkout_item.organization = organization
    checkout_item.save()
    
    return render_template(
        "/item_checkouts/checkout.html",
        form=form,
        organization=organization,
        order=order,
        success=True,
    )


@module.route("/checkout/<checkout_item_id>/delete", methods=["GET", "POST"])
@acl.organization_roles_required(
    "admin", "endorser", "staff", "head", "supervisor supplier"
)
def delete(checkout_item_id):
    """
    ลบรายการเบิกสินค้า (CheckoutItem) ออกจากใบเบิก
    - ทำได้เฉพาะเมื่อใบเบิกยังอยู่ในสถานะ 'pending'
    - เปลี่ยนสถานะของ CheckoutItem เป็น 'disactive'
    """
    organization_id = request.args.get("organization_id")

    checkout_item = models.CheckoutItem.objects(id=checkout_item_id).first()
    
    # ตรวจสอบว่าใบเบิกยังไม่ถูกส่งอนุมัติหรืออนุมัติไปแล้ว
    if checkout_item.order.approval_status != "pending":
        # หากใบเบิกถูกดำเนินการไปแล้ว จะไม่สามารถลบได้
        return redirect(
            url_for(
                "item_checkouts.bill_checkout",
                order_id=checkout_item.order.id,
                organization_id=organization_id,
            )
        )
        
    # เปลี่ยนสถานะเป็น 'disactive' (Soft Delete)
    checkout_item.status = "disactive"
    checkout_item.save()
    
    return redirect(
        url_for(
            "item_checkouts.bill_checkout",
            order_id=checkout_item.order.id,
            organization_id=organization_id,
        )
    )


@module.route("/order/<order_id>/upload_file_items", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "supervisor supplier")
def upload_file(order_id):
    """
    หน้าสำหรับอัปโหลดไฟล์ Excel เพื่อเพิ่มรายการเบิกสินค้าจำนวนมาก
    - เฉพาะ admin และ supervisor supplier
    """
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    form = forms.items.UploadFileForm()
    errors = request.args.getlist("errors")
    order = models.OrderItem.objects(id=order_id).first()

    if not form.validate_on_submit():
        return render_template(
            "/item_checkouts/upload_file.html",
            organization=organization,
            errors=errors,
            form=form,
            order_id=order.id,
            order=order,
        )

    if form.upload_file.data:
        # ตรวจสอบความถูกต้องของข้อมูลในไฟล์
        errors = utils.item_checkouts.validate_items_upload_engagement(
            form.upload_file.data, organization
        )
        if not errors:
            # ประมวลผลไฟล์และเพิ่มข้อมูลลงในใบเบิก
            completed = utils.item_checkouts.process_items_upload_file(
                form.upload_file.data, organization, order
            )
        else:
            # หากมีข้อผิดพลาด ให้แสดงผล
            return render_template(
                "/item_checkouts/upload_file.html",
                organization=organization,
                errors=errors,
                form=form,
                order_id=order_id,
                order=order,
            )
    else:
        # หากไม่มีไฟล์แนบมา
        return redirect(
            url_for(
                "item_checkouts.upload_file",
                organization_id=organization_id,
                errors=["ไม่พบไฟล์"],
                order_id=order_id,
            )
        )
        
    # เมื่อสำเร็จ กลับไปที่หน้ารายการสินค้าในบิล
    return redirect(
        url_for(
            "item_checkouts.bill_checkout",
            organization_id=organization_id,
            order_id=order.id,
        )
    )
