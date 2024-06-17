import datetime
import pandas
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
    df = pandas.DataFrame(columns=SUPPLIERS_HEADER)
    data = {
        "ชื่อคอลัมน์": [
            SUPPLIERS_HEADER[0],
            "",
            "",
            "",
            "",
            "",
            "",
            SUPPLIERS_HEADER[1],
            SUPPLIERS_HEADER[2],
            SUPPLIERS_HEADER[3],
            SUPPLIERS_HEADER[4],
            SUPPLIERS_HEADER[5],
            SUPPLIERS_HEADER[6],
            SUPPLIERS_HEADER[7],
            SUPPLIERS_HEADER[8],
        ],
        "ประเภทข้อมูล": [
            "ตัวอักษร",
            "",
            "",
            "",
            "",
            "",
            "",
            "ตัวอักษร",
            "ตัวอักษร",
            "ตัวอักษร",
            "ตัวอักษร",
            "ตัวอักษร",
            "ตัวอักษร",
            "ตัวอักษร",
            "ตัวอักษร",
        ],
        "ความต้องการ": [
            "จำเป็น",
            "",
            "",
            "",
            "",
            "",
            "",
            "จำเป็น",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
        ],
        "ขอบเขตตัวเลือก": [
            "person",
            "market",
            "incorporated",
            "company limited",
            "corporation limited",
            "public company limited",
            "partnership limited",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
        ],
        "ความหมายตัวเลือก": [
            "บุคคล",
            "ร้านค้า",
            "บริษัท / Inc.",
            "บริษัทจำกัด / Co., Ltd.",
            "บริษัทจำกัด (ขนาดใหญ่) / Corp., Ltd.",
            "บริษัทจำกัด (มหาชน) / Pub Co., Ltd.",
            "ห้างหุ้นส่วนจำกัด / Part., Ltd.",
            "",
            "",
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
            "",
            "",
            "อย่างน้อย ควรใส่ชื่อร้าน/บริษัท หรือชื่อบุคคล อย่างใดอย่างนึง",
            "",
            "",
            "ควรปรับรูปแบบให้เป็นตัวอักษร",
            "ควรปรับรูปแบบให้เป็นตัวอักษร",
            "",
        ],
    }
    description = pandas.DataFrame(data)
    excel_output = BytesIO()
    with pandas.ExcelWriter(excel_output) as writer:
        workbook = writer.book

        df.to_excel(writer, sheet_name="ข้อมูล", index=False)
        description.to_excel(writer, sheet_name="คำอธิบาย", index=False)

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
        df = pandas.read_excel(file)
    except:
        return "กรุณาอัปโหลดเอกสารโดยใช้ Excel Format 2007"

    if len(df.columns) != len(SUPPLIERS_HEADER):
        return "คอลัมน์ไม่ตรงกัน"

    for column in SUPPLIERS_HEADER:
        if column not in df.columns:
            return f"ไม่พบ {column} ในหัวตาราง"

    for idx, row in df.iterrows():
        if pandas.isnull(row["ประเภทผู้จัดหาสินค้า"]):
            return f"ไม่พบประเภทผู้จัดหาสินค้าในบรรทัดที่ {idx+2}"

        if row["ประเภทผู้จัดหาสินค้า"].strip() not in [
            "person",
            "market",
            "incorporated",
            "company limited",
            "corporation limited",
            "public company limited",
            "partnership limited",
        ]:
            return (
                f"ประเภทผู้จัดหาสินค้า '{row['ประเภทผู้จัดหาสินค้า']}' ไม่ถูกต้องในบรรทัดที่ {idx+2} "
            )

        if pandas.isnull(row["เลขผู้เสียภาษี"]):
            return f"ไม่พบเลขผู้เสียภาษีในบรรทัดที่ {idx+2}"

        if pandas.isnull(row["ที่อยู่"]):
            return f"ไม่พบที่อยู่ในบรรทัดที่ {idx+2}"


def process_supplier_file(file, organization, user):
    df = pandas.read_excel(file)

    for idx, row in df.iterrows():

        supplier = models.Supplier()
        supplier.company_name = (
            str(row["ชื่อร้าน/บริษัท"]) if not pandas.isnull(row["ชื่อร้าน/บริษัท"]) else ""
        )
        supplier.person_name = (
            str(row["ชื่อบุคคล"]) if not pandas.isnull(row["ชื่อบุคคล"]) else ""
        )
        supplier.supplier_type = row["ประเภทผู้จัดหาสินค้า"].strip()
        supplier.description = (
            str(row["คำอธิบาย"]) if not pandas.isnull(row["คำอธิบาย"]) else ""
        )
        supplier.address = str(row["ที่อยู่"])
        supplier.tax_id = str(row["เลขผู้เสียภาษี"])
        supplier.email = str(row["อีเมล"]) if not pandas.isnull(row["อีเมล"]) else ""
        supplier.person_phone = (
            str(row["เบอร์โทรมือถือ"]) if not pandas.isnull(row["เบอร์โทรมือถือ"]) else ""
        )
        supplier.company_phone = (
            str(row["เบอร์โทรร้านค้า/บริษัท"])
            if not pandas.isnull(row["เบอร์โทรร้านค้า/บริษัท"])
            else ""
        )
        supplier.organization = organization
        supplier.created_by = user
        supplier.last_modifier = user
        supplier.save()
    return True
