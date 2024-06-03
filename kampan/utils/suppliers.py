import datetime
import pandas as pd
from io import BytesIO
from flask_login import current_user
from flask import send_file
from kampan import models


SUPPLIERS_HEADER = [
    "ประเภทผู้จัดหาสินค้า",
    "เลขผู้เสียภาษี",
    "ชื่อร้าน/บริษัท",
    "ชื่อบุคคล",
    "ที่อยู่",
    "คำอธิบาย",
    "เบอร์โทรมือถือ",
    "เบอร์โทรร้านค้า/บริษัท",
    "อีเมล",
]


def get_template_supplier_file():
    df = pd.DataFrame(columns=SUPPLIERS_HEADER)

    excel_output = BytesIO()
    with pd.ExcelWriter(excel_output) as writer:
        workbook = writer.book
        sheet_name = "upload_inventory"

        df.to_excel(writer, sheet_name=sheet_name, index=False)

        workbook.close()

    excel_output.seek(0)
    response = send_file(
        excel_output,
        as_attachment=True,
        download_name="template_upload_supplier_file.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    return response


def validate_supplier_engagement(file):
    try:
        df = pd.read_excel(file)
    except:
        return "กรุณาอัปโหลดเอกสารโดยใช้ Excel Format 2007"

    if len(df.columns) != len(SUPPLIERS_HEADER):
        return "คอลัมน์ไม่ตรงกัน"

    for column in SUPPLIERS_HEADER:
        if column not in df.columns:
            return f"ไม่พบ {column} ในหัวตาราง"

    for idx, row in df.iterrows():
        if pd.isnull(row["ประเภทผู้จัดหาสินค้า"]):
            return f"ไม่พบประเภทผู้จัดหาสินค้าในบรรทัดที่ {idx+2}"

        if row["ประเภทผู้จัดหาสินค้า"] not in [
            "person",
            "market",
            "incorporated",
            "company limited",
            "corporation limited",
            "public company limited",
            "partnership limited",
        ]:
            return (
                f"ประเภทผู้จัดหาสินค้า  '{row['ประเภทผู้จัดหาสินค้า']}'  ไม่ถูกต้องในบรรทัดที่ {idx+2} "
            )

        if pd.isnull(row["เลขผู้เสียภาษี"]):
            return f"ไม่พบเลขผู้เสียภาษีในบรรทัดที่ {idx+2}"

        if pd.isnull(row["ที่อยู่"]):
            return f"ไม่พบที่อยู่ในบรรทัดที่ {idx+2}"


def process_supplier_file(file, organization, user):
    df = pd.read_excel(file)

    for idx, row in df.iterrows():

        supplier = models.Supplier()
        supplier.company_name = (
            row["ชื่อร้าน/บริษัท"] if not pd.isnull(row["ชื่อร้าน/บริษัท"]) else ""
        )
        supplier.person_name = row["ชื่อบุคคล"] if not pd.isnull(row["ชื่อบุคคล"]) else ""
        supplier.supplier_type = row["ประเภทผู้จัดหาสินค้า"]
        supplier.description = row["คำอธิบาย"] if not pd.isnull(row["คำอธิบาย"]) else ""
        supplier.address = row["ที่อยู่"]
        supplier.tax_id = row["เลขผู้เสียภาษี"]
        supplier.email = row["อีเมล"] if not pd.isnull(row["อีเมล"]) else ""
        supplier.person_phone = (
            row["เบอร์โทรมือถือ"] if not pd.isnull(row["เบอร์โทรมือถือ"]) else ""
        )
        supplier.company_phone = (
            row["เบอร์โทรร้านค้า/บริษัท"] if not pd.isnull(row["เบอร์โทรร้านค้า/บริษัท"]) else ""
        )
        supplier.organization = organization
        supplier.created_by = user
        supplier.save()
    return True
