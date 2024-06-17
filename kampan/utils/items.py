import datetime
import pandas as pd
from io import BytesIO
from flask_login import current_user
from flask import send_file
from kampan import models


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
]


def get_template_items_file():
    df = pd.DataFrame(columns=ITEMS_HEADER)

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
        download_name="template_upload_items_file.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    return response


def validate_items_engagement(file):
    try:
        df = pd.read_excel(file)
    except:
        return "กรุณาอัปโหลดเอกสารโดยใช้ Excel Format 2007"

    if len(df.columns) != len(ITEMS_HEADER):
        return "คอลัมน์ไม่ตรงกัน"

    for column in ITEMS_HEADER:
        if column not in df.columns:
            return f"ไม่พบ {column} ในหัวตาราง"

    for idx, row in df.iterrows():
        if pd.isnull(row["ชื่อ"]):
            return f"ไม่พบชื่อในบรรทัดที่ {idx+2}"

        if pd.isnull(row["หมวดหมู่"]):
            return f"ไม่พบหมวดหมู่ในบรรทัดที่ {idx+2}"

        if row["รูปแบบวัสดุ"] not in ["หนึ่งต่อหนึ่ง", "หนึ่งต่อหลายๆ"]:
            return f"รูปแบบวัสดุ  '{row['รูปแบบวัสดุ']}'  ไม่ถูกต้องในบรรทัดที่ {idx+2} "

        if pd.isnull(row["จำนวนขั้นต่ำที่ต้องการแจ้งเตือน (ขั้นต่ำของหน่วยนับใหญ่)"]):
            return f"ไม่พบ จำนวนขั้นต่ำที่ต้องการแจ้งเตือน ในบรรทัดที่ {idx+2}"
        try:
            number = int(row["จำนวนขั้นต่ำที่ต้องการแจ้งเตือน (ขั้นต่ำของหน่วยนับใหญ่)"])
        except:
            return f"จำนวนขั้นต่ำที่ต้องการแจ้งเตือน ในบรรทัดที่ {idx+2} ไม่ใช่ตัวเลข '{row['จำนวนขั้นต่ำที่ต้องการแจ้งเตือน (ขั้นต่ำของหน่วยนับใหญ่)']}'"

        if pd.isnull(row["จำนวน (หน่วยนับเล็กต่อหน่วยนับใหญ่)"]):
            return f"ไม่พบ จำนวน (หน่วยนับเล็กต่อหน่วยนับใหญ่) ในบรรทัดที่ {idx+2}"
        try:
            number = int(row["จำนวน (หน่วยนับเล็กต่อหน่วยนับใหญ่)"])
        except:
            return f"จำนวน (หน่วยนับเล็กต่อหน่วยนับใหญ่) ในบรรทัดที่ {idx+2} ไม่ใช่ตัวเลข '{row['จำนวน (หน่วยนับเล็กต่อหน่วยนับใหญ่)']}'"


def process_items_file(file, organization, user):
    df = pd.read_excel(file)

    for idx, row in df.iterrows():
        print("---->", idx)
        # item = models.Item(
        #     name=row["ชื่อ"],
        #     description=row["คำอธิบาย"] if pd.isnull(row["คำอธิบาย"]) else "-",
        #     organization=organization,
        #     item_format=(
        #         "one to many" if row["รูปแบบวัสดุ"] == "หนึ่งต่อหลายๆ" else "one to one"
        #     ),
        #     categories=row["หมวดหมู่"],
        #     set_=1,
        #     set_unit="ชุด" if pd.isnull(row["หน่วยนับใหญ่"]) else row["หน่วยนับใหญ่"],
        #     piece_unit="ชิ้น" if pd.isnull(row["หน่วยนับเล็ก"]) else row["หน่วยนับเล็ก"],
        #     piece_per_set=(
        #         1
        #         if pd.isnull(row["จำนวน (หน่วยนับเล็กต่อหน่วยนับใหญ่)"])
        #         else int(row["จำนวน (หน่วยนับเล็กต่อหน่วยนับใหญ่)"])
        #     ),
        #     minimum=(
        #         1
        #         if pd.isnull(row["จำนวนขั้นต่ำที่ต้องการแจ้งเตือน (ขั้นต่ำของหน่วยนับใหญ่)"])
        #         else int(row["จำนวนขั้นต่ำที่ต้องการแจ้งเตือน (ขั้นต่ำของหน่วยนับใหญ่)"])
        #     ),
        #     barcode_id=row["บาร์โค๊ด"],
        #     created_by=user,
        # )
        item = models.items.Item()
        item.image = None
        item.name = row["ชื่อ"]
        item.description = row["คำอธิบาย"] if not pd.isnull(row["คำอธิบาย"]) else "-"
        item.organization = organization
        item.item_format = (
            "one to many" if row["รูปแบบวัสดุ"] == "หนึ่งต่อหลายๆ" else "one to one"
        )
        item.categories = row["หมวดหมู่"]
        item.set_unit = "ชุด" if pd.isnull(row["หน่วยนับใหญ่"]) else row["หน่วยนับใหญ่"]
        item.piece_unit = (
            ("ชิ้น" if pd.isnull(row["หน่วยนับใหญ่"]) else row["หน่วยนับใหญ่"])
            if pd.isnull(row["หน่วยนับเล็ก"])
            else row["หน่วยนับเล็ก"]
        )
        item.piece_per_set = (
            1
            if pd.isnull(row["จำนวน (หน่วยนับเล็กต่อหน่วยนับใหญ่)"])
            else int(row["จำนวน (หน่วยนับเล็กต่อหน่วยนับใหญ่)"])
        )
        item.minimum = (
            1
            if pd.isnull(row["จำนวนขั้นต่ำที่ต้องการแจ้งเตือน (ขั้นต่ำของหน่วยนับใหญ่)"])
            else int(row["จำนวนขั้นต่ำที่ต้องการแจ้งเตือน (ขั้นต่ำของหน่วยนับใหญ่)"])
        )
        item.barcode_id = str(row["บาร์โค๊ด"]) if row["บาร์โค๊ด"] else ""
        item.created_by = user
        item.save()
    return True
