import mongoengine as me
import pandas as pd
import datetime
import re
import io
from .. import models
from decimal import Decimal


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
    """
    errors = []
    processed_user = models.User.objects(id=user_id).first()
    document = models.Document.objects(id=document.id).first()
    if not document:
        document.status = "failed"
        document.updated_date = datetime.datetime.now()
        document.updated_by = processed_user
        document.save()
        print(f"Document {document.id} not found.")
        return False

    try:
        document.file.seek(0)
        df = pd.read_excel(document.file)
        df.columns = df.columns.str.strip()
    except Exception as e:
        document.status = "failed"
        print(f"Error reading Excel in save_mas_db: {e}")
        return False

    print(f"\n==== Loaded Excel File: {len(df)} rows ====\n")
    if not processed_user:
        document.status = "failed"
        print("Cannot find user.")
        return False

    created_count = 0

    for i, row in df.iterrows():
        required_fields = {
            "mas_code": row.get("mas_code"),
            "main_category": row.get("main_category"),
            "sub_category": row.get("sub_category"),
            "name": row.get("name"),
            "item_description": row.get("item_description"),
            "amount": row.get("amount"),
            "budget": row.get("budget"),
            "actual_cost": row.get("actual_cost"),
        }
        missing = [
            key for key, value in required_fields.items() if is_missing_required(value)
        ]

        name = row.get("name")
        if not isinstance(name, str):
            msg = f"Skipped MAS #{i + 1}: name is not a string"
            document.status = "incomplete"
            errors.append(msg)
            continue
        if name is not None and len(name.strip()) < 3:
            missing.append("name (too short)")
        if missing:
            document.status = "incomplete"
            msg = f"Skipped MAS #{i + 1}: missing required fields -- {missing}"
            errors.append(msg)
            continue

        mas_code = safe_str(row.get("mas_code"))
        print(f"Checking MAS code: '{mas_code}'")
        if not mas_code:
            document.status = "failed"
            continue

        mas = models.MAS.objects(mas_code=mas_code, status="active").first()
        if mas:
            msg = f"MAS with code '{mas_code}' already exists. Skipping creation."
            document.status = "incomplete"
            errors.append(msg)
            continue

        mas_obj = models.MAS(
            mas_code=mas_code,
            main_category=safe_str(row.get("main_category")),
            sub_category=safe_str(row.get("sub_category")),
            name=safe_str(row.get("name")),
            item_description=safe_str(row.get("item_description")),
            amount=to_decimal(row.get("amount")),
            budget=to_decimal(row.get("budget")),
            actual_cost=to_decimal(row.get("actual_cost")),
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
        "อื่นๆ": "other",
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
            print(f"Saved procurement: {procurement.product_number}")
        except Exception as e:
            msg = f"Row {idx+1} error: {e}"
            print(msg)
            errors.append(msg)
            continue

    document.updated_date = datetime.datetime.now()
    document.status = "completed"
    document.save()
    print(f"Document status: {document.status}")
    print(f"Total MAs created: {len(df) - len(errors)}/{len(df)}")

    return True
