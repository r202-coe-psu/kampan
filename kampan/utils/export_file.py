import io
import datetime
from openpyxl import Workbook
import pandas as pd
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter
from openpyxl.styles import Font, Alignment, Border, Side

from kampan import models
from kampan.models import mas
from kampan.models.export_file import ExportFile
from kampan.utils.upload_files import MAS_COLUMN_MAP

MAS_COLUMNS = list(MAS_COLUMN_MAP.keys())


def style_openpyxl_header(ws, headers):
    # สร้าง style component ต่าง ๆ
    font = Font(bold=True)  # ตัวหนา
    alignment = Alignment(horizontal="center", vertical="center")  # จัดกลาง
    border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )

    # วนทุกคอลัมน์ของ Header
    for col_idx, header_name in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx)
        cell.value = header_name
        cell.font = font
        cell.alignment = alignment
        cell.border = border


def get_last_data_in_object(obj_data):
    """ดึงค่าข้อมูลสุดท้ายที่ไม่ใช่ค่าว่างจาก list"""
    for item in reversed(obj_data):
        if item not in (None, []):
            return item
    return ""


def process_mas_export(current_user):
    # 1. Query ข้อมูล
    mas_qs = models.MAS.objects(status="active")

    # 2. สร้าง Workbook และ Worksheet
    wb = Workbook()
    ws = wb.active
    ws.title = "ข้อมูลบุคลากร"

    # 3. กำหนด Header (ชื่อคอลัมน์)
    headers = list(MAS_COLUMN_MAP.values())
    ws.append(headers)
    style_openpyxl_header(ws, headers)

    # 4. วนลูปใส่ข้อมูล
    for m in mas_qs:
        row = [
            m.mas_code,  # รหัสแหล่งเงิน
            m.name,  # ชื่อแหล่งเงิน
            m.amount,  # งบประมาณทั้งหมด
            m.remaining_amount,  # งบประมาณที่คงเหลือ
            m.reservable_amount,  # งบประมาณที่สามารถจองได้
        ]
        ws.append(row)

    # set format ทุก column เป็น text
    start_row = 2
    end_row = 10000
    for col_idx in range(1, ws.max_column + 1):
        col_letter = get_column_letter(col_idx)
        # set ความกว้าง column
        ws.column_dimensions[col_letter].width = 15
        for row in range(start_row, end_row + 1):
            ws[f"{col_letter}{row}"].number_format = "@"

    # set format
    currency_format = "#,##0.00"
    column_formats = {
        "งบประมาณทั้งหมด": currency_format,
        "งบประมาณคงเหลือ": currency_format,
        "งบประมาณที่จองได้": currency_format,
    }
    for col_name, fmt in column_formats.items():
        col_idx = headers.index(col_name) + 1
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = 20
        for row in range(start_row, end_row + 1):
            ws[f"{col_letter}{row}"].number_format = fmt
    if not wb.close:
        wb.close()

    # 5. Save ลง Memory Stream
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)  # เลื่อน pointer กลับไปที่จุดเริ่มต้นไฟล์
    export_mas_file = ExportFile.objects(created_by=current_user).first()

    # บันทึกไฟล์
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"ข้อมูล_MAS_{timestamp}.xlsx"

    if not export_mas_file:
        export_mas_file = ExportFile(
            created_date=datetime.datetime.now(),
            created_by=current_user,
        )
    export_mas_file.updated_date = datetime.datetime.now()
    export_mas_file.updater = current_user
    if not export_mas_file.file:
        export_mas_file.file.put(
            output,
            filename=filename,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    else:
        export_mas_file.file.replace(
            output,
            filename=filename,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    export_mas_file.file_name = filename
    export_mas_file.save()
    return True
