import datetime
import pandas
from io import BytesIO
from flask_login import current_user
from flask import send_file
from kampan import models
from mongoengine import Q

ITEMS_HEADER = [
    "ชื่อ",
    "คำอธิบาย",
    "บาร์โค๊ด",
    "รูปแบบวัสดุ",
    "หมวดหมู่",
    "จำนวนขั้นต่ำที่ต้องการแจ้งเตือน (ขั้นต่ำของหน่วยนับใหญ่)",
    "หน่วยนับใหญ่",
    "หน่วยนับเล็ก",
    "จำนวน (หน่วยนับเล็กต่อหน่วยนับใหญ่)",
    "หมายเหตุ",
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
            lambda name: not models.Item.objects(
                name=name.strip(),
                organization=organization,
                status__ne="disactive",
            ).first(),
            "พบวัสดุชื่อ {value} ซ้ำในระบบ ในบรรทัดที่ {idx} กรุณาตรวจสอบข้อมูล",
            duplicate,
        )

        errors = validate_row_field(
            row,
            "หมวดหมู่",
            idx,
            errors,
            lambda cat: models.Category.objects(name=cat.strip()).first(),
            "ไม่พบหมวดหมู่ที่ชื่อ {value} ในบรรทัดที่ {idx} กรุณาตรวจสอบข้อมูล",
        )

        errors = validate_row_field(
            row,
            "รูปแบบวัสดุ",
            idx,
            errors,
            lambda format: format in VALID_MATERIAL_FORMATS,
            "รูปแบบวัสดุ '{value}' ไม่ถูกต้องในบรรทัดที่ {idx} กรุณาตรวจสอบข้อมูล",
        )

        for field_name in [
            "จำนวนขั้นต่ำที่ต้องการแจ้งเตือน (ขั้นต่ำของหน่วยนับใหญ่)",
            "จำนวน (หน่วยนับเล็กต่อหน่วยนับใหญ่)",
        ]:
            errors = validate_row_field(
                row,
                field_name,
                idx,
                errors,
                lambda num: isinstance(num, (int, float)),
                "{value} ในบรรทัดที่ {idx} ไม่ใช่ตัวเลข กรุณาตรวจสอบข้อมูล",
            )

    return errors


def validate_items_upload_engagement(file, organization):
    df, errors = validate_file(file, ITEMS_HEADER)
    if errors:
        return errors

    errors = validate_items_common_logic(df, organization, errors)
    return errors


def validate_edit_items_engagement(file, organization):
    df, errors = validate_file(file, ITEMS_HEADER[:1])
    if errors:
        return errors

    errors = validate_items_common_logic(df, organization, errors, False)
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
        )
    return errors


def validate_delete_items_engagement(file, organization):
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
        )

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


def process_items_upload_file(file, organization, user):
    df = pandas.read_excel(file)

    for idx, row in df.iterrows():
        item = get_or_create_item(str(row["ชื่อ"]), organization, user)
        update_item_fields(item, row, user, is_new=(item.created_by == user))
        item.organization = organization
        item.save()

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
        inventory_items = models.Inventory.objects(
            item=item, status="active", organization=item.organization
        )
        for inventory_item in inventory_items:
            inventory_item.status = "disactive"
            inventory_item.save()
        item_snapshots = models.ItemSnapshot.objects(
            item=item, status="active", organization=item.organization
        )
        for item_snapshot in item_snapshots:
            item_snapshot.status = "disactive"
            item_snapshot.save()
        checkouts = models.CheckoutItem.objects(
            item=item, status="active", organization=item.organization
        )
        for checkout in checkouts:
            checkout.status = "disactive"
            checkout.save()
        lost_items = models.LostBreakItem.objects(
            item=item, status="active", organization=item.organization
        )
        for lost_item in lost_items:
            lost_item.status = "disactive"
            lost_item.save()
    return True


def get_template_items_file():
    description_data = {
        "ชื่อคอลัมน์": [*ITEMS_HEADER[:4], "", *ITEMS_HEADER[4:]],
        "ประเภทข้อมูล": [
            "ตัวอักษร",
            "ตัวอักษร",
            "ตัวอักษร",
            "ตัวอักษร",
            "",
            "ตัวอักษร",
            "ตัวเลข",
            "ตัวอักษร",
            "ตัวอักษร",
            "ตัวเลข",
            "ตัวอักษร",
        ],
        "ความต้องการ": [
            "จำเป็น",
            "",
            "",
            "จำเป็น",
            "",
            "จำเป็น",
            "จำเป็น",
            "",
            "",
            "จำเป็น",
            "",
        ],
        "ขอบเขตตัวเลือก": [
            "",
            "",
            "",
            "one to one",
            "one to many",
            "ตามชื่อของหมวดหมู่ที่สร้างไว้",
            "",
            "",
            "",
            "",
            "",
        ],
        "ความหมายตัวเลือก": [
            "",
            "",
            "",
            "หนึ่งต่อหนึ่ง",
            "หนึ่งต่อหลายๆ",
            "",
            "",
            "",
            "",
            "",
            "",
        ],
        "หมายเหตุ": [
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "หากมีการใส่หน่วยนับใหญ่แต่ไม่มีการใส่หน่วยนับย่อย หน่วยนับย่อยจะเท่ากับหน่วยนับใหญ่",
            "",
            "",
            "หมายเหตุต่างๆ",
        ],
    }

    description_df = pandas.DataFrame(description_data)

    items_df = pandas.DataFrame(columns=ITEMS_HEADER)

    excel_output = BytesIO()
    with pandas.ExcelWriter(excel_output) as writer:
        items_df.to_excel(writer, sheet_name="ข้อมูล", index=False)
        description_df.to_excel(writer, sheet_name="คำอธิบาย", index=False)

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


def export_data(categories, status, organization):
    data = {key: [] for key in ITEMS_HEADER}

    query = Q()
    query &= Q(organization=organization)
    if categories:
        query &= Q(categories__in=categories)
    if status:
        query &= Q(status=status)
    else:
        query &= Q(status__ne="disactive")
    items = models.Item.objects(query).order_by("categories", "name")
    for item in items:
        data["ชื่อ"].append(item.name)
        data["คำอธิบาย"].append(item.description)
        data["บาร์โค๊ด"].append(item.barcode_id)
        data["รูปแบบวัสดุ"].append(item.item_format)
        data["หมวดหมู่"].append(item.categories.name)
        data["จำนวนขั้นต่ำที่ต้องการแจ้งเตือน (ขั้นต่ำของหน่วยนับใหญ่)"].append(item.minimum)
        data["หน่วยนับใหญ่"].append(item.set_unit)
        data["หน่วยนับเล็ก"].append(item.piece_unit)
        data["จำนวน (หน่วยนับเล็กต่อหน่วยนับใหญ่)"].append(item.piece_per_set)
        data["หมายเหตุ"].append(item.remark)

    df = pandas.DataFrame(data=data)

    excel_output = BytesIO()
    with pandas.ExcelWriter(excel_output) as writer:
        workbook = writer.book

        sheet_name = "ข้อมูล"
        df.to_excel(writer, sheet_name=sheet_name, index=False)
        # verify_columns = df.columns.get_loc("รูปแบบวัสดุ")
        # workesheet = writer.sheets[sheet_name]
        # workesheet.data_validation(
        #     1,
        #     verify_columns,
        #     10000,
        #     verify_columns,
        #     {
        #         "validate": "list",
        #         "source": VALID_MATERIAL_FORMATS,
        #     },
        # )
        workbook.close()

    excel_output.seek(0)
    response = send_file(
        excel_output,
        as_attachment=True,
        download_name="item_data.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    return response


def compare_file(file, categories, status, organization):
    data = {key: [] for key in ITEMS_HEADER + ["วัสดุซ้ำ"]}
    df = pandas.read_excel(file)
    query = Q()
    query &= Q(organization=organization)

    if categories:
        query &= Q(categories__in=categories)
    if status:
        query &= Q(status=status)
    else:
        query &= Q(status__ne="disactive")

    items = models.Item.objects(query).order_by("categories", "name")
    for item in items:
        data["ชื่อ"].append(item.name)
        data["คำอธิบาย"].append(item.description)
        data["บาร์โค๊ด"].append(item.barcode_id)
        data["รูปแบบวัสดุ"].append(item.item_format)
        data["หมวดหมู่"].append(item.categories.name)
        data["จำนวนขั้นต่ำที่ต้องการแจ้งเตือน (ขั้นต่ำของหน่วยนับใหญ่)"].append(item.minimum)
        data["หน่วยนับใหญ่"].append(item.set_unit)
        data["หน่วยนับเล็ก"].append(item.piece_unit)
        data["จำนวน (หน่วยนับเล็กต่อหน่วยนับใหญ่)"].append(item.piece_per_set)
        data["หมายเหตุ"].append(item.remark)
        data["วัสดุซ้ำ"].append("มีแล้ว")

    for idx, row in df.iterrows():
        duplicate_item = models.Item.objects(
            name=str(row["ชื่อ"]).strip(),
            organization=organization,
            status__ne="disactive",
        ).first()
        data["ชื่อ"].append(row["ชื่อ"])
        data["คำอธิบาย"].append(row["คำอธิบาย"])
        data["บาร์โค๊ด"].append(row["บาร์โค๊ด"])
        data["รูปแบบวัสดุ"].append(row["รูปแบบวัสดุ"])
        data["หมวดหมู่"].append(row["หมวดหมู่"])
        data["จำนวนขั้นต่ำที่ต้องการแจ้งเตือน (ขั้นต่ำของหน่วยนับใหญ่)"].append(
            row["จำนวนขั้นต่ำที่ต้องการแจ้งเตือน (ขั้นต่ำของหน่วยนับใหญ่)"]
        )
        data["หน่วยนับใหญ่"].append(row["หน่วยนับใหญ่"])
        data["หน่วยนับเล็ก"].append(row["หน่วยนับเล็ก"])
        data["จำนวน (หน่วยนับเล็กต่อหน่วยนับใหญ่)"].append(row["จำนวน (หน่วยนับเล็กต่อหน่วยนับใหญ่)"])
        data["หมายเหตุ"].append(row["หมายเหตุ"])
        if duplicate_item not in items:
            data["วัสดุซ้ำ"].append("ไม่ซ้ำ")
        else:
            data["วัสดุซ้ำ"].append("ซ้ำ")

    new_df = pandas.DataFrame(data=data)
    excel_output = BytesIO()
    new_df = new_df.sort_values("วัสดุซ้ำ")
    with pandas.ExcelWriter(excel_output) as writer:
        workbook = writer.book

        sheet_name = "ข้อมูล"
        new_df.to_excel(writer, sheet_name=sheet_name, index=False)
        workbook.close()

    excel_output.seek(0)
    response = send_file(
        excel_output,
        as_attachment=True,
        download_name="เปรียบเทียบข้อมูลในระบบ.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    return response
