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


def get_template_items_file():
    df = pandas.DataFrame(columns=ITEMS_HEADER)

    data = {
        "ชื่อคอลัมน์": [
            ITEMS_HEADER[0],
            ITEMS_HEADER[1],
            ITEMS_HEADER[2],
            ITEMS_HEADER[3],
            "",
            ITEMS_HEADER[4],
            ITEMS_HEADER[5],
            ITEMS_HEADER[6],
            ITEMS_HEADER[7],
            ITEMS_HEADER[8],
            ITEMS_HEADER[9],
        ],
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
        download_name="template_upload_items_file.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    return response


def get_template_delete_items_file():
    df = pandas.DataFrame(columns=["ชื่อ"])
    excel_output = BytesIO()
    with pandas.ExcelWriter(excel_output) as writer:
        workbook = writer.book

        df.to_excel(writer, sheet_name="รายการที่ต้องการลบ", index=False)

        workbook.close()

    excel_output.seek(0)
    response = send_file(
        excel_output,
        as_attachment=True,
        download_name="template_delete_items_file.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    return response


def validate_items_engagement(file, organization):
    try:
        df = pandas.read_excel(file)
    except:
        return "กรุณาอัปโหลดเอกสารโดยใช้ Excel Format 2007"

    if len(df.columns) != len(ITEMS_HEADER):

        return "คอลัมน์ไม่ตรงกัน"

    for column in ITEMS_HEADER:
        if column not in df.columns:
            return f"ไม่พบ {column} ในหัวตาราง"

    for idx, row in df.iterrows():
        if pandas.isnull(row["ชื่อ"]):
            return f"ไม่พบชื่อในบรรทัดที่ {idx+2}"
        else:
            if models.Item.objects(
                name=str(row["ชื่อ"]), organization=organization
            ).first():
                return f"พบวัสดุชื่อ {row['ชื่อ']} ซ้ำในระบบ ในบรรทัดที่ {idx+2}"

        if pandas.isnull(row["หมวดหมู่"]):
            return f"ไม่พบหมวดหมู่ในบรรทัดที่ {idx+2}"

        category = models.Category.objects(name=str(row["หมวดหมู่"]).strip()).first()
        if not category:
            return f"ไม่พบหมวดหมู่ที่ชื่อ {row['หมวดหมู่']} ในบรรทัดที่ {idx+2}"
        if row["รูปแบบวัสดุ"] not in ["one to one", "one to many"]:
            return f"รูปแบบวัสดุ  '{row['รูปแบบวัสดุ']}'  ไม่ถูกต้องในบรรทัดที่ {idx+2} "

        if pandas.isnull(row["จำนวนขั้นต่ำที่ต้องการแจ้งเตือน (ขั้นต่ำของหน่วยนับใหญ่)"]):
            return f"ไม่พบ จำนวนขั้นต่ำที่ต้องการแจ้งเตือน ในบรรทัดที่ {idx+2}"
        try:
            number = int(row["จำนวนขั้นต่ำที่ต้องการแจ้งเตือน (ขั้นต่ำของหน่วยนับใหญ่)"])
        except:
            return f"จำนวนขั้นต่ำที่ต้องการแจ้งเตือน ในบรรทัดที่ {idx+2} ไม่ใช่ตัวเลข '{row['จำนวนขั้นต่ำที่ต้องการแจ้งเตือน (ขั้นต่ำของหน่วยนับใหญ่)']}'"

        if pandas.isnull(row["จำนวน (หน่วยนับเล็กต่อหน่วยนับใหญ่)"]):
            return f"ไม่พบ จำนวน (หน่วยนับเล็กต่อหน่วยนับใหญ่) ในบรรทัดที่ {idx+2}"
        try:
            number = int(row["จำนวน (หน่วยนับเล็กต่อหน่วยนับใหญ่)"])
        except:
            return f"จำนวน (หน่วยนับเล็กต่อหน่วยนับใหญ่) ในบรรทัดที่ {idx+2} ไม่ใช่ตัวเลข '{row['จำนวน (หน่วยนับเล็กต่อหน่วยนับใหญ่)']}'"


def process_items_file(file, organization, user):
    df = pandas.read_excel(file)

    for idx, row in df.iterrows():
        item = models.items.Item()
        item.image = None
        item.name = row["ชื่อ"]
        item.description = row["คำอธิบาย"] if not pandas.isnull(row["คำอธิบาย"]) else "-"
        item.organization = organization
        item.item_format = (
            "one to many" if row["รูปแบบวัสดุ"] == "one to many" else "one to one"
        )
        item.categories = models.Category.objects(
            name=str(row["หมวดหมู่"]).strip()
        ).first()
        item.set_unit = "ชุด" if pandas.isnull(row["หน่วยนับใหญ่"]) else row["หน่วยนับใหญ่"]
        item.piece_unit = (
            ("ชิ้น" if pandas.isnull(row["หน่วยนับใหญ่"]) else row["หน่วยนับใหญ่"])
            if pandas.isnull(row["หน่วยนับเล็ก"])
            else row["หน่วยนับเล็ก"]
        )
        item.piece_per_set = (
            1
            if pandas.isnull(row["จำนวน (หน่วยนับเล็กต่อหน่วยนับใหญ่)"])
            else int(row["จำนวน (หน่วยนับเล็กต่อหน่วยนับใหญ่)"])
        )
        item.minimum = (
            0
            if pandas.isnull(row["จำนวนขั้นต่ำที่ต้องการแจ้งเตือน (ขั้นต่ำของหน่วยนับใหญ่)"])
            else int(row["จำนวนขั้นต่ำที่ต้องการแจ้งเตือน (ขั้นต่ำของหน่วยนับใหญ่)"])
        )
        item.barcode_id = "" if pandas.isnull(row["บาร์โค๊ด"]) else str(row["บาร์โค๊ด"])
        item.remark = "" if pandas.isnull(row["หมายเหตุ"]) else str(row["หมายเหตุ"])
        item.created_by = user
        item.save()
    return True


def validate_edit_items_engagement(file, organization):
    try:
        df = pandas.read_excel(file)
    except:
        return "กรุณาอัปโหลดเอกสารโดยใช้ Excel Format 2007"

    if len(df.columns) != len(ITEMS_HEADER):

        return "คอลัมน์ไม่ตรงกัน"

    for column in ITEMS_HEADER:
        if column not in df.columns:
            return f"ไม่พบ {column} ในหัวตาราง"

    for idx, row in df.iterrows():
        if pandas.isnull(row["ชื่อ"]):
            return f"ไม่พบชื่อในบรรทัดที่ {idx+2}"
        else:
            if not models.Item.objects(
                name=str(row["ชื่อ"]), organization=organization
            ).first():
                return f"ไม่พบวัสดุชื่อ {row['ชื่อ']} ในบรรทัดที่ {idx+2}"

        if pandas.isnull(row["หมวดหมู่"]):
            return f"ไม่พบหมวดหมู่ในบรรทัดที่ {idx+2}"

        category = models.Category.objects(name=str(row["หมวดหมู่"]).strip()).first()
        if not category:
            return f"ไม่พบหมวดหมู่ที่ชื่อ {row['หมวดหมู่']} ในบรรทัดที่ {idx+2}"
        if row["รูปแบบวัสดุ"] not in ["one to one", "one to many"]:
            return f"รูปแบบวัสดุ  '{row['รูปแบบวัสดุ']}'  ไม่ถูกต้องในบรรทัดที่ {idx+2} "

        if pandas.isnull(row["จำนวนขั้นต่ำที่ต้องการแจ้งเตือน (ขั้นต่ำของหน่วยนับใหญ่)"]):
            return f"ไม่พบ จำนวนขั้นต่ำที่ต้องการแจ้งเตือน ในบรรทัดที่ {idx+2}"
        try:
            number = int(row["จำนวนขั้นต่ำที่ต้องการแจ้งเตือน (ขั้นต่ำของหน่วยนับใหญ่)"])
        except:
            return f"จำนวนขั้นต่ำที่ต้องการแจ้งเตือน ในบรรทัดที่ {idx+2} ไม่ใช่ตัวเลข '{row['จำนวนขั้นต่ำที่ต้องการแจ้งเตือน (ขั้นต่ำของหน่วยนับใหญ่)']}'"

        if pandas.isnull(row["จำนวน (หน่วยนับเล็กต่อหน่วยนับใหญ่)"]):
            return f"ไม่พบ จำนวน (หน่วยนับเล็กต่อหน่วยนับใหญ่) ในบรรทัดที่ {idx+2}"
        try:
            number = int(row["จำนวน (หน่วยนับเล็กต่อหน่วยนับใหญ่)"])
        except:
            return f"จำนวน (หน่วยนับเล็กต่อหน่วยนับใหญ่) ในบรรทัดที่ {idx+2} ไม่ใช่ตัวเลข '{row['จำนวน (หน่วยนับเล็กต่อหน่วยนับใหญ่)']}'"


def process_edit_items_file(file, organization, user):
    df = pandas.read_excel(file)

    for idx, row in df.iterrows():
        item = models.Item.objects(
            name=str(row["ชื่อ"]), organization=organization
        ).first()
        item.description = row["คำอธิบาย"] if not pandas.isnull(row["คำอธิบาย"]) else "-"
        item.item_format = (
            "one to many" if row["รูปแบบวัสดุ"] == "one to many" else "one to one"
        )
        item.categories = models.Category.objects(
            name=str(row["หมวดหมู่"]).strip()
        ).first()
        item.set_unit = "ชุด" if pandas.isnull(row["หน่วยนับใหญ่"]) else row["หน่วยนับใหญ่"]
        item.piece_unit = (
            ("ชิ้น" if pandas.isnull(row["หน่วยนับใหญ่"]) else row["หน่วยนับใหญ่"])
            if pandas.isnull(row["หน่วยนับเล็ก"])
            else row["หน่วยนับเล็ก"]
        )
        item.piece_per_set = (
            1
            if pandas.isnull(row["จำนวน (หน่วยนับเล็กต่อหน่วยนับใหญ่)"])
            else int(row["จำนวน (หน่วยนับเล็กต่อหน่วยนับใหญ่)"])
        )
        item.minimum = (
            0
            if pandas.isnull(row["จำนวนขั้นต่ำที่ต้องการแจ้งเตือน (ขั้นต่ำของหน่วยนับใหญ่)"])
            else int(row["จำนวนขั้นต่ำที่ต้องการแจ้งเตือน (ขั้นต่ำของหน่วยนับใหญ่)"])
        )
        item.barcode_id = "" if pandas.isnull(row["บาร์โค๊ด"]) else str(row["บาร์โค๊ด"])
        item.remark = "" if pandas.isnull(row["หมายเหตุ"]) else str(row["หมายเหตุ"])
        item.last_updated_by = user
        if item.status == "disactive":
            item.status = "pending"
        item.save()
    return True


def validate_delete_items_engagement(file, organization):
    try:
        df = pandas.read_excel(file)
    except:
        return "กรุณาอัปโหลดเอกสารโดยใช้ Excel Format 2007"

    if len(df.columns) != 1:

        return "คอลัมน์ไม่ตรงกัน"
    for column in ["ชื่อ"]:
        if column not in df.columns:
            return f"ไม่พบ {column} ในหัวตาราง"

        for idx, row in df.iterrows():
            if pandas.isnull(row["ชื่อ"]):
                return f"ไม่พบชื่อในบรรทัดที่ {idx+2}"
            else:
                if not models.Item.objects(
                    name=str(row["ชื่อ"]), organization=organization
                ).first():
                    return f"ไม่พบวัสดุชื่อ {row['ชื่อ']} ในระบบ ในบรรทัดที่ {idx+2}"


def process_delete_items_file(file, organization, user):
    df = pandas.read_excel(file)

    for idx, row in df.iterrows():
        item = models.Item.objects(
            name=str(row["ชื่อ"]), organization=organization
        ).first()
        item.status = "disactive"
        item.save()


def export_data(categories, status):
    data = {key: [] for key in ITEMS_HEADER}

    qurry = Q()
    if categories:
        for category in categories:
            qurry |= Q(categories=category)
    if status:
        qurry &= Q(status=status)
    items = models.Item.objects(qurry).order_by("categories", "name")
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
        #         "source": ["one to one", "one to many"],
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
