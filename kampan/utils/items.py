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
    "รูปแบบอุปกรณ์",
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
