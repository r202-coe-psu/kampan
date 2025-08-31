import pandas as pd
import re
from io import BytesIO
from datetime import datetime
from kampan.models.procurement import Procurement, ToRYear
from kampan.models import OrganizationUserRole
from kampan.models import User


def upload_procurement_excel(file_bytes, user_id):
    # อ่านไฟล์ Excel จาก bytes
    df = pd.read_excel(BytesIO(file_bytes))

    # กำหนด mapping ชื่อ column (Excel) -> field ใน Procurement
    column_map = {
        "ชื่อรายการ": "name",
        "รหัสครุภัณฑ์": "asset_code",
        "วันที่เริ่มต้น": "start_date",
        "วันที่สิ้นสุด": "end_date",
        "จำนวนเงิน": "amount",
        "จำนวน (งวด)": "period",
        "ประเภท": "category",
        "ชื่อผู้รับผิดชอบ": "responsible_by",
        "ชื่อบริษัท/ร้านค้า ผู้จำหน่ายผลิตภัณฑ์": "company",
    }

    # สำหรับ mapping category ภาษาไทย -> key
    category_map = {
        "ซอฟต์แวร์": "software",
        "ครุภัณฑ์": "product",
        "จ้างเหมาบริการ": "service",
        "อื่นๆ": "other",
    }

    # แปลงวันที่
    def parse_date(val):
        if isinstance(val, str):
            val = val.strip()
            th_to_en_month = {
                "มกราคม": "January",
                "กุมภาพันธ์": "February",
                "มีนาคม": "March",
                "เมษายน": "April",
                "พฤษภาคม": "May",
                "มิถุนายน": "June",
                "กรกฎาคม": "July",
                "สิงหาคม": "August",
                "กันยายน": "September",
                "ตุลาคม": "October",
                "พฤศจิกายน": "November",
                "ธันวาคม": "December",
            }
            m = re.match(r"(\d{1,2})\s+([ก-๙]+)\s+(\d{4})", val)
            if m:
                day = m.group(1)
                th_month = m.group(2)
                year = int(m.group(3)) - 543
                en_month = th_to_en_month.get(th_month)
                if en_month:
                    date_str = f"{day} {en_month} {year}"
                    try:
                        from datetime import datetime

                        dt = datetime.strptime(date_str, "%d %B %Y")
                        return dt
                    except Exception:
                        pass
            try:
                return pd.to_datetime(val, errors="coerce")
            except Exception:
                return None
        else:
            return pd.to_datetime(val, errors="coerce")

    user = User.objects(id=user_id).first()

    required_columns = [
        "ชื่อรายการ",
        "รหัสครุภัณฑ์",
        "วันที่เริ่มต้น",
        "วันที่สิ้นสุด",
        "จำนวนเงิน",
        "จำนวน (งวด)",
        "ประเภท",
        "ชื่อผู้รับผิดชอบ",
        "ชื่อบริษัท/ร้านค้า ผู้จำหน่ายผลิตภัณฑ์",
        "ปีงบประมาณ",
    ]

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
            # --- ดึงปีงบประมาณจาก column ---
            tor_year_value = row.get("ปีงบประมาณ")
            tor_year_obj = None
            if pd.notnull(tor_year_value):
                tor_year_str = str(int(tor_year_value))
                tor_year_obj = ToRYear.objects(
                    year=tor_year_str, status="active"
                ).first()
                if not tor_year_obj:
                    tor_year_obj = ToRYear(
                        year=tor_year_str,
                        started_date=datetime(int(tor_year_str) - 1, 10, 1),
                        ended_date=datetime(int(tor_year_str), 9, 30),
                        created_by=user,
                        last_updated_by=user,
                        status="active",
                    )
                    tor_year_obj.save()

            for excel_col, model_field in column_map.items():
                value = row.get(excel_col)
                try:
                    if model_field in ["start_date", "end_date"]:
                        value = parse_date(value)
                    if model_field == "amount":
                        value = float(value) if pd.notnull(value) else 0
                    if model_field == "period":
                        value = int(value) if pd.notnull(value) else 1
                    if model_field == "asset_code":
                        value = str(value) if pd.notnull(value) else ""
                    if model_field == "category":
                        value = category_map.get(str(value).strip(), "other")
                    if model_field == "responsible_by":
                        responsible_by_list = []
                        names = str(value).strip().splitlines()
                        for name in names:
                            name = name.strip()
                            if not name:
                                continue
                            fullname = name.split(" ", 1)
                            if len(fullname) == 2:
                                first_name, last_name = fullname
                                user_role = OrganizationUserRole.objects(
                                    first_name=first_name.strip(),
                                    last_name=last_name.strip(),
                                ).first()
                                if user_role:
                                    responsible_by_list.append(user_role)
                        data[model_field] = responsible_by_list
                        continue  # skip the assignment below for responsible_by
                    data[model_field] = value
                except Exception as field_e:
                    print(f"Row {idx+1} field '{excel_col}' error: {field_e}")

            # ตรวจสอบข้อมูลซ้ำ
            duplicate_query = {
                "name": data.get("name"),
                "asset_code": data.get("asset_code"),
                "start_date": data.get("start_date"),
                "end_date": data.get("end_date"),
                "amount": data.get("amount"),
                "period": data.get("period"),
                "company": data.get("company"),
                "category": data.get("category"),
                "responsible_by": data.get("responsible_by"),
                "tor_year": tor_year_obj,
            }
            if Procurement.objects(**duplicate_query).first():
                print(f"Row {idx+1} skipped: duplicate found.")
                continue

            # สร้าง product_number ตามปีงบประมาณ
            product_number = Procurement.generate_product_number(tor_year=tor_year_obj)
            procurement = Procurement(
                **data,
                product_number=product_number,
                tor_year=tor_year_obj,
                created_by=user,
                last_updated_by=user,
                status="active",  # <-- set status to active on upload
            )
            procurement.save()
            print(f"Saved procurement: {procurement.product_number}")
        except Exception as e:
            print(f"Row {idx+1} error: {e}")
            continue
