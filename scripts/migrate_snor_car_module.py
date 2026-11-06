#!/usr/bin/env python3
"""
Migration: ระบบรถ สนอ. แยกเป็นโมดูล snor_car แทน Organization.car_flow

- ลบ field car_flow ออกจากทุก org (model ไม่มี field นี้แล้ว org ที่ยังมีจะโหลดไม่ได้)
- ถ้าระบุ --snor-organization ให้เพิ่ม "snor_car" ใน enabled_modules ของ org นั้น
  (org ที่ enabled_modules ยังไม่เคยตั้ง = เปิดทุกโมดูลอยู่แล้ว ไม่ต้องแตะ)

รันซ้ำได้ และมี --dry-run

    .venv/bin/python scripts/migrate_snor_car_module.py --dry-run --snor-organization <org_id>
    .venv/bin/python scripts/migrate_snor_car_module.py --snor-organization <org_id>
"""

import argparse

from bson import ObjectId


def migrate(db, snor_organization_id=None, dry_run=False, log=print):
    prefix = "[dry-run] " if dry_run else ""

    with_car_flow = {"car_flow": {"$exists": True}}
    log(f"{prefix}remove car_flow from {db.organizations.count_documents(with_car_flow)} organization(s)")
    if not dry_run:
        db.organizations.update_many(with_car_flow, {"$unset": {"car_flow": ""}})

    if not snor_organization_id:
        return

    organization = db.organizations.find_one({"_id": ObjectId(snor_organization_id)})
    if organization is None:
        raise SystemExit(f"organization {snor_organization_id} not found")

    modules = organization.get("enabled_modules")
    if modules is None:
        log(f"{prefix}{organization['name']}: modules never set, snor_car already on")
    elif "snor_car" in modules:
        log(f"{prefix}{organization['name']}: snor_car already enabled")
    else:
        log(f"{prefix}{organization['name']}: enable snor_car")
        if not dry_run:
            db.organizations.update_one({"_id": organization["_id"]}, {"$push": {"enabled_modules": "snor_car"}})


def main():
    from pymongo import MongoClient

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="mongodb://localhost:27017")
    parser.add_argument("--db", default="kampandb")
    parser.add_argument("--snor-organization")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    migrate(MongoClient(args.host)[args.db], snor_organization_id=args.snor_organization, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
