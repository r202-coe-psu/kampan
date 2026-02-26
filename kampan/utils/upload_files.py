import mongoengine as me
import pandas as pd
import datetime
import re
import io
from .. import models
from decimal import Decimal

# ---- MAS column map: field_name → Thai label (used for template headers & import remap) ----
MAS_COLUMN_MAP = {
    "mas_code": "รหัสแหล่งเงิน (MAS Code)",
    "name": "ชื่อรายการ",
    "amount": "งบประมาณทั้งหมด",
    "remaining_amount": "งบประมาณคงเหลือ",
    "reservable_amount": "งบประมาณที่จองได้",
}
# Keep list aliases for backward-compat (column detection in view)
MAS_COLUMNS = list(MAS_COLUMN_MAP.keys())

# ---- MA column map: field_name → Thai label ----
MA_COLUMN_MAP = {
    "product_number": "เลขที่สินค้า/เลขที่เอกสาร",
    "name": "ชื่อรายการ",
    "asset_code": "รหัสครุภัณฑ์",
    "start_date": "วันที่เริ่มต้น",
    "end_date": "วันที่สิ้นสุด",
    "amount": "จำนวนเงิน(บาท)",
    "period": "จำนวนงวด",
    "category": "ประเภท",
    "responsible_by": "ผู้รับผิดชอบ",
    "company": "บริษัท",
}
MA_COLUMNS = list(MA_COLUMN_MAP.keys())


def _normalize_columns(df: pd.DataFrame, column_map: dict) -> pd.DataFrame:
    """Rename Thai label columns back to English field names if needed."""
    reverse = {v: k for k, v in column_map.items()}
    return df.rename(columns=reverse)


def generate_mas_template() -> io.BytesIO:
    """Return a BytesIO containing an xlsx template for MAS import (Thai headers)."""
    df = pd.DataFrame(columns=list(MAS_COLUMN_MAP.values()))
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="MAS")
    buf.seek(0)
    return buf


def generate_ma_template() -> io.BytesIO:
    """Return a BytesIO containing an xlsx template for MA (Procurement) import (Thai headers)."""
    df = pd.DataFrame(columns=list(MA_COLUMN_MAP.values()))
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="MA")
    buf.seek(0)
    return buf


def to_decimal(val):
    try:
        return Decimal(str(val))
    except Exception:
        return Decimal("0.00")


def safe_split(value, sep=","):
    if isinstance(value, str):
        return [v.strip() for v in value.split(sep)]
    elif value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    else:
        return [v.strip() for v in str(value).split(sep)]


def safe_str(value):
    if isinstance(value, str):
        return value.strip()
    elif value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    else:
        return str(value).strip()


def is_missing_required(value):
    return (
        value is None
        or (isinstance(value, float) and pd.isna(value))
        or str(value).strip() == ""
    )


def save_mas_db(document, mas, user_id):
    print("=====> Start processing MAS document:", document.id)
    """
    อ่านข้อมูล MAS จากไฟล์ Excel แล้วสร้าง MAS แต่ละตัวลงฐานข้อมูล

    Expected columns: mas_code, name, amount, remaining_amount, reservable_amount
    """
    errors = []
    processed_user = models.User.objects(id=user_id).first()
    document = models.Document.objects(id=document.id).first()
    if not document:
        print(f"Document not found.")
        return False, []

    try:
        document.file.seek(0)
        df = pd.read_excel(document.file)
        df.columns = df.columns.str.strip()
        df = _normalize_columns(df, MAS_COLUMN_MAP)
    except Exception as e:
        document.status = "failed"
        document.save()
        print(f"Error reading Excel in save_mas_db: {e}")
        return False, []

    print(f"\n==== Loaded Excel File: {len(df)} rows ====\n")
    if not processed_user:
        document.status = "failed"
        document.save()
        print("Cannot find user.")
        return False, []

    required_cols = {
        "mas_code",
        "name",
        "amount",
        "remaining_amount",
        "reservable_amount",
    }
    missing_cols = required_cols - set(col.lower() for col in df.columns)
    if missing_cols:
        document.status = "failed"
        document.save()
        msg = f"Missing required columns: {missing_cols}"
        print(msg)
        return False, [msg]

    created_count = 0

    for i, row in df.iterrows():
        required_fields = {
            "mas_code": row.get("mas_code"),
            "name": row.get("name"),
            "amount": row.get("amount"),
            "remaining_amount": row.get("remaining_amount"),
            "reservable_amount": row.get("reservable_amount"),
        }
        missing = [k for k, v in required_fields.items() if is_missing_required(v)]
        if missing:
            document.status = "incomplete"
            msg = f"Skipped MAS #{i + 1}: missing required fields -- {missing}"
            errors.append(msg)
            print(msg)
            continue

        name = safe_str(row.get("name"))
        if len(name) < 3:
            msg = f"Skipped MAS #{i + 1}: name too short ('{name}')"
            document.status = "incomplete"
            errors.append(msg)
            print(msg)
            continue

        mas_code = safe_str(row.get("mas_code"))
        if not mas_code:
            msg = f"Skipped MAS #{i + 1}: mas_code is empty"
            document.status = "incomplete"
            errors.append(msg)
            print(msg)
            continue

        existing = models.MAS.objects(mas_code=mas_code, status="active").first()
        if existing:
            msg = f"MAS with code '{mas_code}' already exists. Skipping."
            document.status = "incomplete"
            errors.append(msg)
            print(msg)
            continue

        amount = to_decimal(row.get("amount"))
        remaining_amount = to_decimal(row.get("remaining_amount"))
        reservable_amount = to_decimal(row.get("reservable_amount"))

        mas_obj = models.MAS(
            mas_code=mas_code,
            name=name,
            amount=amount,
            remaining_amount=remaining_amount,
            reservable_amount=reservable_amount,
            status="active",
            created_by=processed_user,
            last_updated_by=processed_user,
            created_date=datetime.datetime.now(),
            updated_date=datetime.datetime.now(),
        )
        mas_obj.save()
        created_count += 1
        print(f"Created MAS #{i + 1}: {mas_obj.name}")

    document.updated_date = datetime.datetime.now()
    if created_count == 0:
        document.status = "failed"
    elif created_count != len(df):
        document.status = "incomplete"
    else:
        document.status = "completed"
    document.save()
    print(f"Document status: {document.status}")
    print(f"Total MASs created: {created_count}/{len(df)}")

    return True, errors


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


def save_ma_db(document, ma, user_id):
    print("=====> Start processing MA document:", document.id)
    """
    อ่านข้อมูล MA จากไฟล์ Excel แล้วสร้าง MA แต่ละตัวลงฐานข้อมูล
    """
    errors = []
    processed_user = models.User.objects(id=user_id).first()
    document = models.Document.objects(id=document.id).first()
    created_count = 0
    if not document:
        document.status = "failed"
        document.updated_date = datetime.datetime.now()
        document.updated_by = processed_user
        document.save()
        print(f"Document {document.id} not found.")
        return False

    try:
        document.file.seek(0)
        file_bytes = document.file.read()
        df = pd.read_excel(io.BytesIO(file_bytes))
        df.columns = df.columns.str.strip()
        df = _normalize_columns(df, MA_COLUMN_MAP)
    except Exception as e:
        document.status = "failed"
        print(f"Error reading Excel in save_ma_db: {e}")
        return False

    print(f"\n==== Loaded Excel File: {len(df)} rows ====\n")
    if not processed_user:
        document.status = "failed"
        print("Cannot find user.")
        return False

    column_map = {
        "product_number": "product_number",
        "name": "name",
        "asset_code": "asset_code",
        "start_date": "start_date",
        "end_date": "end_date",
        "amount": "amount",
        "period": "period",
        "category": "category",
        "responsible_by": "responsible_by",
        "company": "company",
    }
    category_map = {
        "ซอฟต์แวร์": "software",
        "ครุภัณฑ์": "product",
        "จ้างเหมาบริการ": "service",
        "วัสดุ": "material",
    }

    required_columns = list(column_map.keys())

    for idx, row in df.iterrows():
        missing = False
        for col in required_columns:
            if pd.isnull(row.get(col)) or str(row.get(col)).strip() == "":
                msg = f"Row {idx+1} skipped: missing required column '{col}'."
                print(msg)
                errors.append(msg)
                missing = True
                break
        if missing:
            continue

        data = {}
        try:
            for excel_col, model_field in column_map.items():
                value = row.get(excel_col)
                try:
                    if model_field in ["start_date", "end_date"]:
                        value = parse_date(value)
                    if model_field == "amount":
                        value = (
                            to_decimal(value) if pd.notnull(value) else Decimal("0.00")
                        )
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
                                user_role = models.OrganizationUserRole.objects(
                                    first_name=first_name.strip(),
                                    last_name=last_name.strip(),
                                ).first()
                                if user_role:
                                    responsible_by_list.append(user_role)
                        data[model_field] = responsible_by_list
                        continue
                    data[model_field] = value
                except Exception as field_e:
                    msg = f"Row {idx+1} field '{excel_col}' error: {field_e}"
                    print(msg)
                    errors.append(msg)

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
            }
            if models.Procurement.objects(**duplicate_query).first():
                msg = f"Row {idx+1} skipped: duplicate found."
                print(msg)
                errors.append(msg)
                continue

            procurement = models.Procurement(
                **data,
                created_by=processed_user,
                last_updated_by=processed_user,
                status="active",
            )
            procurement.save()
            created_count += 1
            print(f"Saved procurement: {procurement.product_number}")
        except Exception as e:
            msg = f"Row {idx+1} error: {e}"
            print(msg)
            errors.append(msg)
            continue

    document.updated_date = datetime.datetime.now()
    if created_count == 0:
        document.status = "failed"
    elif created_count < len(df):
        document.status = "incomplete"
    else:
        document.status = "completed"
    document.save()
    print(f"Document status: {document.status}")
    print(f"Total MAs created: {created_count}/{len(df)}")

    return True
