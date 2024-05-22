import datetime
import pandas as pd
from io import BytesIO
from flask_login import current_user
from flask import send_file
from kampan import models


INVENTORY_HEADER = [
    "บาร์โค้ด",
    "ชื่ออุปกรณ์",
    "จำนวน (หน่วยนับใหญ่)",
    "ราคา (ชุดละ)",
    "คลังอุปกรณ์",
    "ตำแหน่ง (คำอธิบาย)",
]


def process_inventory_engagement(inventory_engagement_file):
    df = pd.read_excel(inventory_engagement_file.file)

    df.columns = df.columns.str.strip()
    df = df.dropna(subset=["บาร์โค้ด"])
    organization = models.Organization.objects(
        id=inventory_engagement_file.organization.id,
        status="active",
    ).first()
    for idx, row in df.iterrows():
        item = models.Item.objects(
            name=row["ชื่ออุปกรณ์"],
            barcode_id=str(row["บาร์โค้ด"]),
            status="active",
            organization=organization,
        ).first()

        warehouse = models.Warehouse.objects(
            status="active",
            name=row["คลังอุปกรณ์"],
            organization=organization,
        ).first()

        position = models.ItemPosition.objects(
            status="active",
            description=row["ตำแหน่ง (คำอธิบาย)"],
            warehouse=warehouse,
        ).first()

        inventory = models.Inventory.objects(
            status="pending",
            registration=inventory_engagement_file.registration,
            item=item,
            organization=organization,
        ).first()

        if inventory:
            inventory.set_ = row["จำนวน (หน่วยนับใหญ่)"]
            inventory.quantity = row["จำนวน (หน่วยนับใหญ่)"] * item.piece_per_set
            inventory.remain = row["จำนวน (หน่วยนับใหญ่)"] * item.piece_per_set
            inventory.price = row["ราคา (ชุดละ)"]
            inventory.warehouse = warehouse
            inventory.position = position
            inventory.created_by = current_user._get_current_object()
        else:
            inventory = models.Inventory()
            inventory.status = "pending"
            inventory.registration = inventory_engagement_file.registration
            inventory.warehouse = warehouse
            inventory.organization = organization
            inventory.item = item
            inventory.position = position
            inventory.set_ = row["จำนวน (หน่วยนับใหญ่)"]
            inventory.quantity = row["จำนวน (หน่วยนับใหญ่)"] * item.piece_per_set
            inventory.remain = row["จำนวน (หน่วยนับใหญ่)"] * item.piece_per_set
            inventory.price = row["ราคา (ชุดละ)"]
            inventory.created_by = current_user._get_current_object()

        inventory.save()

    inventory_engagement_file.status = "completed"
    inventory_engagement_file.updated_date = datetime.datetime.now()
    inventory_engagement_file.save()


def check_columns_file(df, default_columns):
    if len(default_columns) != len(df.columns):
        return "จำนวน Columns ของไฟล์ไม่ถูกต้อง"
    for column in df.columns:
        if column not in default_columns:
            return f"ชื่อ Columns : {column} ของไฟล์ไม่ถูกต้อง"


def check_int_values(df_column):
    for value in df_column:
        if type(value) != int:
            return f"ข้อมูล '{value}' ใน Columns ชื่อ '{df_column.name}' ไม่เป็นจำนวนเต็มบวก"
        else:
            if value < 0:
                return (
                    f"ข้อมูล '{value}' ใน Columns ชื่อ '{df_column.name}' ไม่เป็นจำนวนเต็มบวก"
                )


def check_float_values(df_column):
    for value in df_column:
        if type(value) == float or type(value) == int:
            if value < 0:
                return f"ข้อมูล '{value}' ใน Columns ชื่อ '{df_column.name}' ไม่เป็นจำนวนทศนิยมบวก"
        else:
            return f"ข้อมูล '{value}' ใน Columns ชื่อ '{df_column.name}' ไม่เป็นจำนวนทศนิยมบวก"


def check_items(df, organization):
    for idx, row in df.iterrows():
        item = models.Item.objects(
            name=row["ชื่ออุปกรณ์"],
            barcode_id=str(row["บาร์โค้ด"]),
            status="active",
            organization=organization,
        ).first()
        if not item:
            return f"ไม่พบอุปกรณ์ชื่อ : {row['ชื่ออุปกรณ์']} หรือบาร์โค้ดหมายเลข : {row['บาร์โค้ด']} ที่ได้ลงทะเบียนไว้ในคลังอุปกรณ์"


def check_positions(df, organization):
    for idx, row in df.iterrows():
        warehouse = models.Warehouse.objects(
            status="active",
            name=row["คลังอุปกรณ์"],
            organization=organization,
        ).first()
        if not warehouse:
            return f"ไม่พบคลังอุปกรณ์ชื่อ : {row['คลังอุปกรณ์']} ที่ได้ลงทะเบียนไว้"
        position = models.ItemPosition.objects(
            status="active",
            description=row["ตำแหน่ง (คำอธิบาย)"],
            warehouse=warehouse,
        ).first()
        if not position:
            return f"ไม่พบตำแหน่งของอุปกรณ์ : {row['ตำแหน่ง (คำอธิบาย)']} ที่ได้ลงทะเบียนไว้"


def validate_inventory_engagement(inventory_engagement_file):
    df = pd.read_excel(inventory_engagement_file.file)
    df.columns = df.columns.str.strip()
    invalide_column = check_columns_file(df, INVENTORY_HEADER)
    if invalide_column:
        return invalide_column

    invalid_int_value = check_int_values(df["จำนวน (หน่วยนับใหญ่)"])
    if invalid_int_value:
        return invalid_int_value

    invalid_float_value = check_float_values(df["ราคา (ชุดละ)"])
    if invalid_float_value:
        return invalid_float_value

    invalid_items = check_items(df, inventory_engagement_file.organization)
    if invalid_items:
        return invalid_items

    invalid_positions = check_positions(df, inventory_engagement_file.organization)
    if invalid_positions:
        return invalid_positions


def get_template_inventory_file():
    df = pd.DataFrame(columns=INVENTORY_HEADER)

    excel_output = BytesIO()
    with pd.ExcelWriter(excel_output) as writer:
        workbook = writer.book
        sheet_name = "upload_inventory"

        df.to_excel(writer, sheet_name=sheet_name, index=False)

        # text_format = workbook.add_format({"num_format": "@"})
        # worksheet = writer.sheets[sheet_name]
        # worksheet.set_column("A:ZZ", None, text_format)

        workbook.close()

    excel_output.seek(0)
    response = send_file(
        excel_output,
        as_attachment=True,
        download_name="upload_inventory.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    return response
