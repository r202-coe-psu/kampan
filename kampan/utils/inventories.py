import datetime
import pandas as pd
from io import BytesIO
from flask_login import current_user

from kampan import models


INVENTORY_HEADER = [
    "บาร์โค้ด",
    "ชื่ออุปกรณ์",
    "จำนวน (ชุด)",
    "ราคา (ชุดละ)",
    "คลังอุปกรณ์",
    "ตำแหน่ง (คำอธิบาย)",
]


def process_inventory_engagement(inventory_engagement_file):
    df = pd.read_excel(inventory_engagement_file.file)

    # print(sheet_names)
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
            inventory.set_ = row["จำนวน (ชุด)"]
            inventory.quantity = row["จำนวน (ชุด)"] * item.piece_per_set
            inventory.remain = row["จำนวน (ชุด)"] * item.piece_per_set
            inventory.price = row["ราคา (ชุดละ)"]
            inventory.warehouse = warehouse
            inventory.position = position
        else:
            inventory = models.Inventory()
            inventory.status = "pending"
            inventory.registration = inventory_engagement_file.registration
            inventory.warehouse = warehouse
            inventory.organization = organization
            inventory.item = item
            inventory.position = position
            inventory.set_ = row["จำนวน (ชุด)"]
            inventory.quantity = row["จำนวน (ชุด)"] * item.piece_per_set
            inventory.remain = row["จำนวน (ชุด)"] * item.piece_per_set
            inventory.price = row["ราคา (ชุดละ)"]
        inventory.save()
    inventory_engagement_file.status = "completed"
    inventory_engagement_file.updated_date = datetime.datetime.now()
    inventory_engagement_file.save()


def check_columns_file(df, default_columns):
    if len(default_columns) != len(df.columns):
        return "จำนวน Columns ของไฟล์ไม่ถูกต้อง"
    for column in df.columns:
        if column not in default_columns:
            return "ชื่อ Columns ของไฟล์ไม่ถูกต้อง"


def check_int_value(df):
    for value in df:
        if type(value) != int:
            print("error-------")
            return f"มีบางประเภทข้อมูลใน Columns ชื่อ '{df.name}' ไม่เป็นจำนวนเต็มบวก"
        else:
            if value < 0:
                return f"มีบางประเภทข้อมูลใน Columns ชื่อ '{df.name}' ไม่เป็นจำนวนเต็มบวก"


def check_float_value(df):
    for value in df:
        if type(value) == float or type(value) == int:
            if value < 0:
                return f"มีบางประเภทข้อมูลใน Columns ชื่อ '{df.name}' ไม่เป็นจำนวนทศนิยมบวก"
        else:
            return f"มีบางประเภทข้อมูลใน Columns ชื่อ '{df.name}' ไม่เป็นจำนวนทศนิยมบวก"


def validate_inventory_engagement(inventory_engagement_file):
    df = pd.read_excel(inventory_engagement_file.file)
    df.columns = df.columns.str.strip()
    invalide_column = check_columns_file(df, INVENTORY_HEADER)
    if invalide_column:
        return invalide_column

    invalid_int_value = check_int_value(df["จำนวน (ชุด)"])
    if invalid_int_value:
        return invalid_int_value

    invalid_float_value = check_float_value(df["ราคา (ชุดละ)"])
    if invalid_float_value:
        return invalid_float_value
    print(df.dtypes)
