import io
import datetime
from openpyxl import Workbook
import pandas as pd
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill

from kampan import models
from kampan.models import mas
from kampan.models.export_file import ExportFile
from kampan.utils.date_utils import format_date_th

EXPORT_REQUISITION_ITEMS_COLUMN_MAP = {
    "requisition_item": "รายการ",
    "requisition_code": "รหัสครุภัณฑ์",
    "serial_number": "serial number",
    "location": "สถานที่ตั้ง",
    "seller": "ผู้จัดจําหน่าย",
    "insurance_start_date": "วันที่เริ่มประกัน",
    "insurance_end_date": "วันที่สิ้นสุดประกัน",
    "warranty_period": "ระยะเวลาประกัน",
}

EXPORT_REQUISITION_ITEMS_COLUMN_KEYS = list(EXPORT_REQUISITION_ITEMS_COLUMN_MAP.keys())
