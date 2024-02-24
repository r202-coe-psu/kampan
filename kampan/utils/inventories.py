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
    sheet_names = df.keys()
    print(sheet_names)
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
        print("----->", item)
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
            warehouse=warehouse,
            position=position,
            organization=organization,
        ).first()
        if inventory:
            inventory.set_ = row["จำนวน (ชุด)"]
            inventory.quantity = row["จำนวน (ชุด)"] * item.piece_per_set
            inventory.remain = row["จำนวน (ชุด)"] * item.piece_per_set
            inventory.price = row["ราคา (ชุดละ)"]
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
