#!/usr/bin/env python3
"""
Migration: ระบบจองรถออนไลน์เป็นโมดูล car_reservation แทน Organization.car_flow

- ลบ field car_flow ออกจากทุก org (model ไม่มี field นี้แล้ว org ที่ยังมีจะโหลดไม่ได้)
- เปลี่ยนชื่อโมดูลเดิมใน enabled_modules ของทุก org เป็น "car_reservation"
  (org ที่เปิดไว้ตั้งแต่ก่อน rename)
- เปลี่ยนชื่อ collection เดิมเป็น car_reservations / car_reservation_positions (แล้วแปลงเป็น role ตามข้อถัดไป)
  ถ้ามีทั้งชื่อเก่าและใหม่ จะรวมเอกสารเก่าเข้าชื่อใหม่ (เอกสาร _id ซ้ำใช้ของชื่อใหม่)
- แปลงตำแหน่งผู้อนุมัติเดิม (collection car_reservation_positions) เป็น organization role
  ผู้ดำรงตำแหน่งและผู้รักษาการแต่ละคนได้ role ที่ key ตรงกับตำแหน่งใน OrganizationUserRole
  ที่ active ของ org นั้น (คนขับรถไม่ได้ role ผู้อนุมัติ และไม่มีสมาชิก active ก็ข้าม) org ที่ตั้ง
  enabled_roles ไว้จะเพิ่ม role นั้นให้ด้วย แล้วลบ collection ตำแหน่งทิ้ง
- ถ้าระบุ --organization ให้เพิ่ม "car_reservation" ใน enabled_modules ของ org นั้น
  (org ที่ enabled_modules ยังไม่เคยตั้ง = เปิดทุกโมดูลอยู่แล้ว ไม่ต้องแตะ)

รันซ้ำได้ และมี --dry-run

    .venv/bin/python scripts/migrate_car_reservation_module.py --dry-run --organization <org_id>
    .venv/bin/python scripts/migrate_car_reservation_module.py --organization <org_id>
"""

import argparse

from bson import ObjectId

MODULE = "car_reservation"

# ชื่อเดิมก่อน rename ประกอบจากสองท่อนเพื่อไม่ให้คำเดิมค้างอยู่ใน source
LEGACY_MODULE = "sn" + "or_car"

COLLECTION_RENAMES = [
    (LEGACY_MODULE + "_requests", "car_reservations"),
    ("car_flow_positions", "car_reservation_positions"),
]


def _rename_module_key(db, prefix, dry_run, log):
    for organization in db.organizations.find({"enabled_modules": LEGACY_MODULE}):
        modules = []
        for key in organization["enabled_modules"]:
            key = MODULE if key == LEGACY_MODULE else key
            if key not in modules:
                modules.append(key)
        log(f"{prefix}{organization.get('name')}: rename {LEGACY_MODULE} -> {MODULE}")
        if not dry_run:
            db.organizations.update_one({"_id": organization["_id"]}, {"$set": {"enabled_modules": modules}})


def _rename_collection(db, old, new, prefix, dry_run, log):
    if old not in db.list_collection_names():
        return
    if new not in db.list_collection_names():
        log(f"{prefix}rename collection {old} -> {new}")
        if not dry_run:
            db[old].rename(new)
        return
    existing = {doc["_id"] for doc in db[new].find({}, {"_id": 1})}
    missing = [doc for doc in db[old].find() if doc["_id"] not in existing]
    log(f"{prefix}merge collection {old} into {new} ({len(missing)} document(s) moved)")
    if not dry_run:
        if missing:
            db[new].insert_many(missing)
        db[old].drop()


POSITIONS = "car_reservation_positions"


def _convert_positions(db, prefix, dry_run, log):
    if POSITIONS not in db.list_collection_names():
        return
    for position in db[POSITIONS].find():
        role = position.get("position_key")
        organization_ref = position.get("organization")
        if not role or organization_ref is None:
            log(f"{prefix}skip malformed position document {position['_id']}")
            continue
        people = [ref for ref in [position.get("user"), *position.get("delegates", [])] if ref]
        for ref in people:
            members = list(
                db.organization_user_roles.find(
                    {"organization": organization_ref, "user": ref, "status": "active"}
                )
            )
            if not members:
                log(f"{prefix}{role}: user {ref.id} is not an active member, skipped")
            for member in members:
                if "driver" in member["roles"]:
                    log(f"{prefix}{role}: user {ref.id} is a driver, skipped")
                    continue
                if role in member["roles"]:
                    continue
                log(f"{prefix}{role}: add role to user {ref.id}")
                if not dry_run:
                    db.organization_user_roles.update_one(
                        {"_id": member["_id"]}, {"$addToSet": {"roles": role}}
                    )
        organization = db.organizations.find_one({"_id": organization_ref.id})
        enabled = (organization or {}).get("enabled_roles")
        if enabled is not None and role not in enabled:
            log(f"{prefix}{organization.get('name')}: enable role {role}")
            if not dry_run:
                db.organizations.update_one(
                    {"_id": organization["_id"]}, {"$addToSet": {"enabled_roles": role}}
                )
    log(f"{prefix}drop collection {POSITIONS}")
    if not dry_run:
        db[POSITIONS].drop()


def migrate(db, organization_id=None, dry_run=False, log=print):
    prefix = "[dry-run] " if dry_run else ""

    with_car_flow = {"car_flow": {"$exists": True}}
    log(f"{prefix}remove car_flow from {db.organizations.count_documents(with_car_flow)} organization(s)")
    if not dry_run:
        db.organizations.update_many(with_car_flow, {"$unset": {"car_flow": ""}})

    _rename_module_key(db, prefix, dry_run, log)

    for old, new in COLLECTION_RENAMES:
        _rename_collection(db, old, new, prefix, dry_run, log)

    _convert_positions(db, prefix, dry_run, log)

    if not organization_id:
        return

    organization = db.organizations.find_one({"_id": ObjectId(organization_id)})
    if organization is None:
        raise SystemExit(f"organization {organization_id} not found")

    modules = organization.get("enabled_modules")
    if modules is None:
        log(f"{prefix}{organization['name']}: modules never set, {MODULE} already on")
    elif MODULE in modules or LEGACY_MODULE in modules:
        log(f"{prefix}{organization['name']}: {MODULE} already enabled")
    else:
        log(f"{prefix}{organization['name']}: enable {MODULE}")
        if not dry_run:
            db.organizations.update_one({"_id": organization["_id"]}, {"$push": {"enabled_modules": MODULE}})


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
