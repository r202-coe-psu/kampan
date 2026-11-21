#!/usr/bin/env python3
"""
Migration: คำขอใช้รถหนึ่งใบมีได้หลายชุด (รถ + พขร.) ใน car_reservations.assignments

เดิมคำขอเก็บรถ/พขร./OT และรายงานปิดงานทั้งหมดเป็นช่องเดี่ยวบนเอกสารคำขอ ตอนนี้ย้ายไปอยู่ในแต่ละชุด
(CarAssignment) ของ `assignments`:

- คำขอที่ยังไม่มี `assignments` และมีรถหรือ พขร.: สร้างชุดเดียวที่ถือค่าเดิมทุกช่อง (รวมรูปเลขไมล์
  ที่เป็น id ใน GridFS และ is_overtime) พร้อม assignment_id ใหม่ ลง `assignments` แล้ว $unset ช่องเดิม
- คำขอที่ยังไม่มีรถและ พขร.: `assignments: []` แล้ว $unset ช่องเดิมเช่นกัน
- ลบ index เก่า (organization, car, ...) และ (organization, driver, ...) เมื่อไม่เหลือคำขอที่ยังไม่ย้าย
  (index ใหม่บน assignments.car / assignments.driver สร้างโดย MongoEngine ตอนแอปเริ่ม)
  index อื่นไม่แตะ

รันซ้ำได้ (คำขอที่มี assignments แล้วถูกข้าม) และมี --dry-run
รัน scripts/backup-mongodb.py ก่อนรันจริง

    .venv/bin/python scripts/migrate_car_reservation_assignments.py --dry-run --organization <org_id>
    .venv/bin/python scripts/migrate_car_reservation_assignments.py --organization <org_id>
"""

import argparse

from bson import ObjectId

COLLECTION = "car_reservations"

# ช่องเดี่ยวเดิมบนคำขอที่ย้ายเข้า assignment (ชื่อเดียวกับช่องของ CarAssignment)
MOVED_FIELDS = [
    "car",
    "driver",
    "is_overtime",
    "last_mileage",
    "last_mileage_before",
    "fuel_liters",
    "expense_case",
    "cost_baht",
    "started_at",
    "completed_at",
    "closed_ip",
    "mileage_photo_out",
    "mileage_photo_in",
    "mileage_photos_at",
    "closed_off_campus",
    "close_confirmation",
    "close_confirmed_by",
    "close_confirmed_at",
    "close_reported_end",
    "close_dispute_note",
]

NOT_MIGRATED = {"assignments": {"$exists": False}}


def _ref_id(value):
    return getattr(value, "id", value)


def _build_assignment(doc):
    if doc.get("car") is None and doc.get("driver") is None:
        return None
    assignment = {"assignment_id": ObjectId()}
    for name in MOVED_FIELDS:
        if doc.get(name) is not None:
            assignment[name] = doc[name]
    return assignment


def _old_indexes(collection):
    """index (organization, car, ...) และ (organization, driver, ...) ของเดิม หาจากคีย์ ไม่ผูกกับชื่อ index"""
    names = []
    for name, info in collection.index_information().items():
        keys = [key for key, _ in info["key"]]
        if len(keys) > 1 and keys[0] == "organization" and keys[1] in ("car", "driver"):
            names.append(name)
    return names


def _migrate_requests(db, organization_id, prefix, dry_run, log):
    collection = db[COLLECTION]
    wanted = ObjectId(organization_id) if organization_id else None
    migrated = skipped = 0
    for doc in list(collection.find(NOT_MIGRATED)):
        if wanted is not None and _ref_id(doc.get("organization")) != wanted:
            skipped += 1
            continue
        assignment = _build_assignment(doc)
        log(
            f"{prefix}request {doc['_id']}: "
            + ("move car/driver/close-out fields into 1 assignment" if assignment else "no car or driver, set assignments to []")
        )
        migrated += 1
        if not dry_run:
            collection.update_one(
                {"_id": doc["_id"], **NOT_MIGRATED},
                {
                    "$set": {"assignments": [assignment] if assignment else []},
                    "$unset": {name: "" for name in MOVED_FIELDS},
                },
            )
    log(f"{prefix}{migrated} request(s) migrated, {skipped} left alone (other organization)")
    return skipped


def _drop_old_indexes(db, remaining, prefix, dry_run, log):
    collection = db[COLLECTION]
    names = _old_indexes(collection)
    if names and remaining:
        log(f"{prefix}keep old indexes {names}: {remaining} request(s) of other organizations are not migrated yet")
        return
    for name in names:
        log(f"{prefix}drop old index {name}")
        if not dry_run:
            collection.drop_index(name)


def migrate(db, organization_id=None, dry_run=False, log=print):
    prefix = "[dry-run] " if dry_run else ""
    if COLLECTION not in db.list_collection_names():
        log(f"{prefix}no {COLLECTION} collection, nothing to do")
        return
    remaining = _migrate_requests(db, organization_id, prefix, dry_run, log)
    _drop_old_indexes(db, remaining, prefix, dry_run, log)


def main():
    from pymongo import MongoClient

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="mongodb://localhost:27017")
    parser.add_argument("--db", default="kampandb")
    parser.add_argument("--organization")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    migrate(MongoClient(args.host)[args.db], organization_id=args.organization, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
