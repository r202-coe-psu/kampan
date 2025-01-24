import datetime
import pandas
from io import BytesIO
from flask_login import current_user
from flask import send_file
from kampan import models
from mongoengine import Q

ITEMS_HEADER = [
    "ชื่อ",
    "จำนวน",
]

VALID_MATERIAL_FORMATS = ["one to one", "one to many"]


def validate_file(file, required_columns):
    try:
        df = pandas.read_excel(file)
    except Exception:
        return None, ["กรุณาอัปโหลดเอกสารโดยใช้ Excel Format 2007"]

    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        return None, [f"ไม่พบ {col} ในหัวตาราง" for col in missing_columns]

    return df, []


def validate_row_field(
    row,
    field_name,
    idx,
    error_list,
    validator=None,
    error_msg=None,
    validate_duplicate=True,
):
    value = row.get(field_name)
    if pandas.isnull(value) or (isinstance(value, str) and not value.strip()):
        error_list.append(f"ไม่พบ {field_name} ในบรรทัดที่ {idx+2} กรุณากรอกข้อมูล")
        return error_list

    if validate_duplicate:
        if validator and not validator(value):
            error_list.append(error_msg.format(value=value, idx=idx + 2))
            return error_list

    return error_list


def validate_items_common_logic(df, organization, errors, duplicate=True):
    for idx, row in df.iterrows():
        errors = validate_row_field(
            row,
            "ชื่อ",
            idx,
            errors,
            lambda name: models.Item.objects(
                name=name.strip(),
                organization=organization,
                status__ne="disactive",
            ).first(),
            "ไม่พบวัสดุชื่อ {value} ในระบบ ในบรรทัดที่ {idx} กรุณาตรวจสอบข้อมูล",
            duplicate,
        )

    return errors


def validate_items_upload_engagement(file, organization):
    df, errors = validate_file(file, ITEMS_HEADER)
    if errors:
        return errors

    errors = validate_items_common_logic(df, organization, errors)
    return errors


def validate_compare_items_engagement(file, organization):
    df, errors = validate_file(file, ITEMS_HEADER[:1])
    if errors:
        return errors

    for idx, row in df.iterrows():
        errors = validate_row_field(
            row,
            "ชื่อ",
            idx,
            errors,
            lambda name: models.Item.objects(
                name=name.strip(),
                organization=organization,
                status__ne="disactive",
            ).first(),
            "ไม่พบวัสดุชื่อ {value} ในระบบ ในบรรทัดที่ {idx} กรุณาตรวจสอบข้อมูล",
            validate_duplicate=False,
        )
    return errors


def get_item_by_name(name, organization):
    return models.Item.objects(
        name=name.strip(),
        organization=organization,
        status__ne="disactive",
    ).first()


def get_or_create_item(name, organization, user):
    item = get_item_by_name(name, organization)
    if not item:
        item = models.Item()
        item.image = None
        item.created_by = user
    return item


def update_item_fields(item, row, user, is_new=False, active=False):
    item.name = str(row["ชื่อ"]).strip()
    item.description = (
        row.get("คำอธิบาย", "-") if not pandas.isnull(row.get("คำอธิบาย")) else "-"
    )
    if not active:
        item.item_format = (
            "one to many" if row.get("รูปแบบวัสดุ") == "one to many" else "one to one"
        )
    item.categories = models.Category.objects(
        name=str(row.get("หมวดหมู่", "")).strip()
    ).first()
    item.set_unit = (
        row.get("หน่วยนับใหญ่", "ชุด") if not pandas.isnull(row.get("หน่วยนับใหญ่")) else "ชุด"
    )
    item.piece_unit = (
        row.get("หน่วยนับเล็ก", row.get("หน่วยนับใหญ่", "ชิ้น"))
        if not pandas.isnull(row.get("หน่วยนับเล็ก"))
        else row.get("หน่วยนับใหญ่", "ชิ้น")
    )
    if not active:
        item.piece_per_set = (
            int(row.get("จำนวน (หน่วยนับเล็กต่อหน่วยนับใหญ่)", 1))
            if not pandas.isnull(row.get("จำนวน (หน่วยนับเล็กต่อหน่วยนับใหญ่)"))
            else 1
        )
    item.minimum = (
        int(row.get("จำนวนขั้นต่ำที่ต้องการแจ้งเตือน (ขั้นต่ำของหน่วยนับใหญ่)", 0))
        if not pandas.isnull(row.get("จำนวนขั้นต่ำที่ต้องการแจ้งเตือน (ขั้นต่ำของหน่วยนับใหญ่)"))
        else 0
    )
    item.barcode_id = (
        str(row.get("บาร์โค๊ด", "")) if not pandas.isnull(row.get("บาร์โค๊ด")) else ""
    )
    item.remark = (
        str(row.get("หมายเหตุ", "")) if not pandas.isnull(row.get("หมายเหตุ")) else ""
    )
    item.last_updated_by = user
    if is_new:
        item.created_by = user


def process_items_upload_file(file, organization, order):
    df = pandas.read_excel(file)

    for idx, row in df.iterrows():
        item = models.Item.objects(name=str(row.get("ชื่อ", "")).strip()).first()
        if item:
            checkout_item = models.CheckoutItem.objects(item=item).first()
            if not checkout_item:
                checkout_item = models.CheckoutItem()
            checkout_item.user = current_user._get_current_object()
            checkout_item.order = order
            checkout_item.item = item
            checkout_item.piece = int(row.get("จำนวน", 0))
            checkout_item.quantity = int(row.get("จำนวน", 0))
            checkout_item.organization = organization
            checkout_item.save()
    return True


def process_edit_items_file(file, organization, user):
    df = pandas.read_excel(file)

    for idx, row in df.iterrows():
        item = get_item_by_name(str(row["ชื่อ"]), organization)
        if not item:
            continue

        if item.status == "active":
            update_item_fields(item, row, user, active=True)

        item.save()

    return True


def process_delete_items_file(file, organization, user):
    df = pandas.read_excel(file)

    for idx, row in df.iterrows():
        item = get_item_by_name(str(row["ชื่อ"]), organization)
        if item:
            item.status = "disactive"
            item.last_updated_by = user
            item.save()

    return True


def get_template_items_file():

    items_df = pandas.DataFrame(columns=ITEMS_HEADER)

    excel_output = BytesIO()
    with pandas.ExcelWriter(excel_output) as writer:
        items_df.to_excel(writer, sheet_name="ข้อมูล", index=False)

    excel_output.seek(0)

    return send_file(
        excel_output,
        as_attachment=True,
        download_name="รูปแบบไฟล์การอัปโหลดวัสดุ.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def get_template_delete_items_file():
    df = pandas.DataFrame(columns=["ชื่อ"])
    excel_output = BytesIO()
    with pandas.ExcelWriter(excel_output) as writer:
        workbook = writer.book
        df.to_excel(writer, sheet_name="รายการที่ต้องการลบ", index=False)
        workbook.close()

    excel_output.seek(0)
    return send_file(
        excel_output,
        as_attachment=True,
        download_name="รูปแบบไฟล์การลบวัสดุ.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
