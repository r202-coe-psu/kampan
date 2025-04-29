import datetime
import pandas
from io import BytesIO
from flask_login import current_user
from flask import send_file
from kampan import models


INVENTORY_HEADER = [
    # "บาร์โค้ด",
    "ชื่อวัสดุ",
    "จำนวน (หน่วยนับใหญ่)",
    "ราคา (หน่วยใหญ่ละ)",
    "คลังวัสดุ",
    # "ตำแหน่ง (คำอธิบาย)",
]


def get_template_inventory_file():
    df = pandas.DataFrame(columns=INVENTORY_HEADER)
    data = {
        "ชื่อคอลัมน์": [
            INVENTORY_HEADER[0],
            INVENTORY_HEADER[1],
            INVENTORY_HEADER[2],
            INVENTORY_HEADER[3],
            # INVENTORY_HEADER[4],
            # INVENTORY_HEADER[5],
        ],
        "ประเภทข้อมูล": [
            # "ตัวอักษร",
            "ตัวอักษร",
            "ตัวเลข",
            "ตัวเลข",
            "ตัวอักษร",
            # "ตัวอักษร",
        ],
        "ความต้องการ": [
            # "",
            "จำเป็น",
            "จำเป็น",
            "จำเป็น",
            "จำเป็น",
            # "จำเป็น",
        ],
        "ขอบเขตตัวเลือก": [
            # "ใส่บาร์โค๊ดของวัสดุที่ต้องการ (หากมี)",
            "ใส่ชื่อของวัสดุที่ต้องการ",
            "",
            "",
            "ใส่ชื่อของคลังที่ต้องการ",
            # "ใส่ตำแหน่งที่ต้องการ",
        ],
        "ความหมายตัวเลือก": [
            # "",
            "",
            "",
            "",
            "",
            # "",
        ],
        "หมายเหตุ": [
            # "",
            "",
            "",
            "",
            "",
            # "",
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
        download_name="upload_inventory.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    return response


def process_inventory_engagement(inventory_engagement_file, organization):
    df = pandas.read_excel(inventory_engagement_file.file)

    df.columns = df.columns.str.strip()

    for idx, row in df.iterrows():

        item = models.Item.objects(
            name=str(row["ชื่อวัสดุ"]).strip(),
            status="active",
            organization=organization,
        ).first()

        warehouse = models.Warehouse.objects(
            status="active",
            name=row["คลังวัสดุ"],
            organization=organization,
        ).first()

        inventory = models.Inventory.objects(
            status="pending",
            registration=inventory_engagement_file.registration,
            item=item,
            organization=organization,
        ).first()

        if not inventory:
            inventory = models.Inventory(
                status="pending",
                registration=inventory_engagement_file.registration,
                organization=organization,
                item=item,
            )

        # inventory.position = position
        inventory.set_ = row["จำนวน (หน่วยนับใหญ่)"]
        inventory.quantity = row["จำนวน (หน่วยนับใหญ่)"] * item.piece_per_set
        inventory.remain = row["จำนวน (หน่วยนับใหญ่)"] * item.piece_per_set
        inventory.warehouse = warehouse
        inventory.price = row["ราคา (หน่วยใหญ่ละ)"]
        inventory.created_by = current_user._get_current_object()
        inventory.save()

    inventory_engagement_file.status = "completed"
    inventory_engagement_file.upandasated_date = datetime.datetime.now()
    inventory_engagement_file.save()


# def check_columns_file(df, default_columns):
#     if len(default_columns) != len(df.columns):
#         return "จำนวน Columns ของไฟล์ไม่ถูกต้อง"
#     for column in df.columns:
#         if column not in default_columns:
#             return f"ชื่อ Columns : {column} ของไฟล์ไม่ถูกต้อง"


# def check_int_values(df_column):
#     for value in df_column:
#         if type(value) != int:
#             return f"ข้อมูล '{value}' ใน Columns ชื่อ '{df_column.name}' ไม่เป็นจำนวนเต็มบวก"
#         else:
#             if value < 0:
#                 return (
#                     f"ข้อมูล '{value}' ใน Columns ชื่อ '{df_column.name}' ไม่เป็นจำนวนเต็มบวก"
#                 )


# def check_float_values(df_column):
#     for value in df_column:
#         if type(value) == float or type(value) == int:
#             if value < 0:
#                 return f"ข้อมูล '{value}' ใน Columns ชื่อ '{df_column.name}' ไม่เป็นจำนวนทศนิยมบวก"
#         else:
#             return f"ข้อมูล '{value}' ใน Columns ชื่อ '{df_column.name}' ไม่เป็นจำนวนทศนิยมบวก"


# def check_items(df, organization):
#     for idx, row in df.iterrows():
#         if pandas.isnull(row["บาร์โค้ด"]):
#             item = models.Item.objects(
#                 name=str(row["ชื่อวัสดุ"]).strip(),
#                 status="active",
#                 organization=organization,
#             ).first()
#             if not item:
#                 return f"ไม่พบวัสดุชื่อ : {row['ชื่อวัสดุ']} ที่ได้ลงทะเบียนไว้ในคลังวัสดุ"
#         else:
#             item = models.Item.objects(
#                 name=str(row["ชื่อวัสดุ"]).strip(),
#                 barcode_id=str(row["บาร์โค้ด"]).strip(),
#                 status="active",
#                 organization=organization,
#             ).first()
#             if not item:
#                 return f"ไม่พบวัสดุชื่อ : {row['ชื่อวัสดุ']} หรือบาร์โค้ดหมายเลข : {row['บาร์โค้ด']} ที่ได้ลงทะเบียนไว้ในคลังวัสดุ"


# def check_positions(df, organization):
#     for idx, row in df.iterrows():
#         warehouse = models.Warehouse.objects(
#             status="active",
#             name=str(row["คลังวัสดุ"] if not pandas.isnull(row["คลังวัสดุ"]) else ""),
#             organization=organization,
#         ).first()
#         if not warehouse:
#             return f"ไม่พบคลังวัสดุชื่อ : {row['คลังวัสดุ']} ที่ได้ลงทะเบียนไว้"
# position = models.ItemPosition.objects(
#     status="active",
#     description=str(
#         row["ตำแหน่ง (คำอธิบาย)"]
#         if not pandas.isnull(row["ตำแหน่ง (คำอธิบาย)"])
#         else ""
#     ),
#     warehouse=warehouse,
# ).first()
# if not position:
#     return f"ไม่พบตำแหน่งของวัสดุ : {row['ตำแหน่ง (คำอธิบาย)']} ที่ได้ลงทะเบียนไว้"


# def validate_inventory_engagement(inventory_engagement_file):
#     df = pandas.read_excel(inventory_engagement_file.file)
#     df.columns = df.columns.str.strip()
#     invalide_column = check_columns_file(df, INVENTORY_HEADER)
#     if invalide_column:
#         return invalide_column

#     invalid_int_value = check_int_values(df["จำนวน (หน่วยนับใหญ่)"])
#     if invalid_int_value:
#         return invalid_int_value

#     invalid_float_value = check_float_values(df["ราคา (หน่วยใหญ่ละ)"])
#     if invalid_float_value:
#         return invalid_float_value

#     invalid_items = check_items(df, inventory_engagement_file.organization)
#     if invalid_items:
#         return invalid_items

# invalid_positions = check_positions(df, inventory_engagement_file.organization)
# if invalid_positions:
#     return invalid_positions


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


def validate_upload_inventory_engagement(file, organization):
    df, errors = validate_file(file, INVENTORY_HEADER)
    if errors:
        return errors

    for idx, row in df.iterrows():
        errors = validate_row_field(
            row,
            "ชื่อวัสดุ",
            idx,
            errors,
            lambda name: models.Item.objects(
                name=name.strip(),
                status="active",
                organization=organization,
            ).first(),
            "ไม่พบวัสดุชื่อ {value} ในระบบ ในบรรทัดที่ {idx} กรุณาตรวจสอบข้อมูล",
        )

        errors = validate_row_field(
            row,
            "จำนวน (หน่วยนับใหญ่)",
            idx,
            errors,
            lambda num: isinstance(num, (int, float)),
            "{value} ในบรรทัดที่ {idx} ไม่ใช่ตัวเลข กรุณาตรวจสอบข้อมูล",
        )

        errors = validate_row_field(
            row,
            "ราคา (หน่วยใหญ่ละ)",
            idx,
            errors,
            lambda num: isinstance(num, (int, float)),
            "{value} ในบรรทัดที่ {idx} ไม่ใช่ตัวเลข กรุณาตรวจสอบข้อมูล",
        )

        errors = validate_row_field(
            row,
            "คลังวัสดุ",
            idx,
            errors,
            lambda name: models.Warehouse.objects(
                status="active",
                name=name.strip(),
                organization=organization,
            ).first(),
            "ไม่พบคลังชื่อ {value} ในระบบ ในบรรทัดที่ {idx} กรุณาตรวจสอบข้อมูล",
        )

    return errors
