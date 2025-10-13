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
    อ่านข้อมูล KPI จากไฟล์ Excel แล้วสร้าง KPI แต่ละตัวลงฐานข้อมูล
    """
    errors = []
    document.status = "completed"
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
    document.save()
    print(f"Document status: {document.status}")
    print(f"Total MAS created: {created_count}/{len(df)}")

    return True, errors


def save_ma_db(document, ma):
    print("=====> Start processing MA document:", document.id)
    return
