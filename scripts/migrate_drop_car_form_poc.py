#!/usr/bin/env python3
"""
Migration: ล้างข้อมูล POC car form templates (branch poc-car-application) ออกจาก DB

โค้ดระบบรถไม่มี car form template แล้ว และ MongoEngine โหลดเอกสารที่มี field ที่ model ไม่รู้จักไม่ได้
(FieldDoesNotExist) script นี้จึง:
- ย้ายคำขอที่สร้างจาก template (มี form_template) ไปเก็บที่ car_applications_poc_archive
- ลบ field ของ POC ออกจากคำขอที่เหลือ
- rename car_form_templates / car_form_paper_files เป็น *_poc_archive (ไม่ลบทิ้ง ย้อนกลับได้)

รันซ้ำได้ และมี --dry-run

    .venv/bin/python scripts/migrate_drop_car_form_poc.py --dry-run
    .venv/bin/python scripts/migrate_drop_car_form_poc.py --host mongodb://localhost:27017 --db kampandb
"""

import argparse

POC_FIELDS = (
    "form_template",
    "template_snapshot",
    "details",
    "current_step",
    "step_approvals",
    "audit_logs",
    "assigned_vehicle_type",
)
ARCHIVED_COLLECTIONS = ("car_form_templates", "car_form_paper_files")
ARCHIVE_SUFFIX = "_poc_archive"


def migrate(db, dry_run=False, log=print):
    prefix = "[dry-run] " if dry_run else ""

    from_template = list(db.car_applications.find({"form_template": {"$exists": True, "$ne": None}}))
    log(f"{prefix}archive {len(from_template)} request(s) made from templates")
    if not dry_run:
        for application in from_template:
            db.car_applications_poc_archive.replace_one({"_id": application["_id"]}, application, upsert=True)
            db.car_applications.delete_one({"_id": application["_id"]})

    with_poc_fields = {"$or": [{field: {"$exists": True}} for field in POC_FIELDS]}
    count = db.car_applications.count_documents(with_poc_fields)
    log(f"{prefix}remove POC fields from {count} request(s)")
    if not dry_run:
        db.car_applications.update_many(with_poc_fields, {"$unset": {field: "" for field in POC_FIELDS}})

    names = db.list_collection_names()
    for name in ARCHIVED_COLLECTIONS:
        if name not in names:
            continue
        archive = name + ARCHIVE_SUFFIX
        log(f"{prefix}rename {name} ({db[name].count_documents({})} docs) -> {archive}")
        if dry_run:
            continue
        if archive in names:
            for document in db[name].find():
                db[archive].replace_one({"_id": document["_id"]}, document, upsert=True)
            db[name].drop()
        else:
            db[name].rename(archive)


def main():
    from pymongo import MongoClient

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="mongodb://localhost:27017")
    parser.add_argument("--db", default="kampandb")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    migrate(MongoClient(args.host)[args.db], dry_run=args.dry_run)


if __name__ == "__main__":
    main()
