import pandas as pd
import re
from io import BytesIO
from datetime import datetime
from kampan.models.mas import MAS
from kampan.models import OrganizationUserRole
from kampan.models import User, UploadHistory
from flask import send_file


def upload_mas_excel(file_bytes, user_id, filename, file_id):
    # อ่านไฟล์ Excel จาก bytes
    user = User.objects(id=user_id).first()
    df = pd.read_excel(BytesIO(file_bytes))

    mas_code_col = None
    for col in df.columns:
        if "รหัส" in col and "เงิน" in col:
            mas_code_col = col
            break
    print(df.columns)
    column_map = {
        mas_code_col: "mas_code",
        "หมวดรายจ่าย": "main_category",
        "หมวดรายจ่ายย่อย": "sub_category",
        "ชื่อรายการ": "name",
        "รายละเอียด": "item_description",
        "จำนวนเงิน (บาท)": "amount",
        "ประมาณจ่าย (บาท)": "budget",
        "จ่ายจริง (บาท)": "actual_cost",
    }

    required_columns = list(column_map.keys())
    for idx, row in df.iterrows():
        # ตรวจสอบว่าข้อมูลในแต่ละ column ที่จำเป็นครบหรือไม่
        missing = False
        for col in required_columns:
            if pd.isnull(row.get(col)) or str(row.get(col)).strip() == "":
                print(f"Row {idx+1} skipped: missing required column '{col}'.")
                missing = True
                break
        if missing:
            continue

        data = {}
        try:
            for excel_col, model_field in column_map.items():
                value = row.get(excel_col)
                try:
                    if model_field == "amount":
                        value = float(value) if pd.notnull(value) else 0
                    if model_field == "budget":
                        value = int(value) if pd.notnull(value) else 0
                    if model_field == "actual_cost":
                        value = str(value) if pd.notnull(value) else 0
                    if model_field in [
                        "mas_code",
                        "main_category",
                        "sub_category",
                        "name",
                        "item_description",
                    ]:
                        value = str(value).strip() if pd.notnull(value) else ""
                    data[model_field] = value
                except Exception as field_e:
                    print(f"Row {idx+1} field '{excel_col}' error: {field_e}")

            # ตรวจสอบข้อมูลซ้ำ
            duplicate_query = {
                "mas_code": data.get("mas_code"),
                "main_category": data.get("main_category"),
                "sub_category": data.get("sub_category"),
                "name": data.get("name"),
                "item_description": data.get("item_description"),
                "amount": data.get("amount"),
                "budget": data.get("budget"),
                "actual_cost": data.get("actual_cost"),
            }
            if MAS.objects(**duplicate_query).first():
                print(f"Row {idx+1} skipped: duplicate found.")
                continue

            mas_record = MAS(
                **data,
                created_by=user,
                last_updated_by=user,
                status="active",
            )
            mas_record.save()
            print(f"Saved mas {MAS.mas_code}")
        except Exception as e:
            print(f"Row {idx+1} error: {e}")
            continue
        except Exception as e:
            print(f"Row {idx+1} error: {e}")
            continue

    upload_history = UploadHistory(
        file_name=filename,
        file_type="mas",
        file_id=file_id,
        uploaded_by=user,
        upload_date=datetime.now(),
    )
    upload_history.save()


def download_mas_template():
    template_data = {
        "รหัสแหล่งเงิน": ["2568-001"],
        "หมวดรายจ่าย": ["CC"],
        "หมวดรายจ่ายย่อย": ["CC"],
        "ชื่อรายการ": ["CC"],
        "รายละเอียด": ["CC"],
        "จำนวนเงิน (บาท)": [50000],
        "ประมาณจ่าย (บาท)": [50000],
        "จ่ายจริง (บาท)": [50000],
    }
    df = pd.DataFrame(template_data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="แม่แบบข้อมูล", index=False)
        worksheet = writer.sheets["แม่แบบข้อมูล"]
        for column in worksheet.columns:
            max_length = max((len(str(cell.value)) for cell in column), default=0)
            column_letter = column[0].column_letter
            worksheet.column_dimensions[column_letter].width = min(max_length + 2, 50)
    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name="Template_MAS.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
