#!/usr/bin/env python3
"""
Migration script: ปรับปรุงข้อมูลคำขอใช้รถยนต์กรณี 'ไปต่างจังหวัด' (out of town)
สำหรับระบบที่มีข้อมูลเดิมอยู่ในฐานข้อมูล

หน้าที่ของ script:
- ตรวจสอบ CarApplication กรณี 'out of town' ที่ตกค้างอยู่ในสถานะ 'pending on director'
  โดยที่ยังไม่เคยผ่านการอนุมัติจากหัวหน้าฝ่าย (header_approval is None)
  และยังไม่เคยผ่านการจัดสรรรถ/คนขับจากพัสดุ (admin_approval is None)
- ปรับสถานะกลับมาเป็น 'pending on header' เพื่อให้เริ่มเข้าสู่กระบวนการอนุมัติแบบใหม่
  (หัวหน้าฝ่ายอนุมัติ -> พัสดุจัดสรรรถ/คนขับ -> ผอ. อนุมัติขั้นสุดท้าย)
- รองรับการทำงานแบบ --dry-run เพื่อดูข้อมูลที่จะถูกแก้ไขก่อนบันทึกจริง
"""

import argparse
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from flask import Flask
from kampan import models


def migrate_car_applications(dry_run=False):
    print("=" * 70)
    print(f"[*] Starting CarApplication Out-of-Town Migration (dry_run={dry_run})")
    print("=" * 70)

    # ค้นหาคำขอใช้รถกรณีไปต่างจังหวัดที่ค้างอยู่สถานะ pending on director จากระบบเดิม
    query = models.vehicle_applications.CarApplication.objects(
        using_type="out of town",
        status="pending on director",
    )

    total_candidates = query.count()
    print(f"[*] Found {total_candidates} out-of-town application(s) in 'pending on director' status.")

    migrated_count = 0
    skipped_count = 0

    for car_app in query:
        # ตรวจสอบว่าคำขอนี้สร้างจากระบบเดิมหรือไม่:
        # ระบบเดิม: สร้างปุ๊บ status = "pending on director", ไม่มีทั้ง header_approval และ admin_approval
        # ระบบใหม่: จะเป็น "pending on director" ก็ต่อเมื่อ admin_approval มีค่าแล้ว (พัสดุอนุมัติและเสนอ ผอ.)
        has_admin_approval = bool(car_app.admin_approval and car_app.admin_approval.approved_by)
        has_header_approval = bool(car_app.header_approval and car_app.header_approval.approved_by)

        creator_name = car_app.creator.get_name() if car_app.creator else "Unknown"
        created_str = car_app.created_date.strftime("%Y-%m-%d %H:%M") if car_app.created_date else "-"

        if not has_admin_approval and not has_header_approval:
            # เข้าเงื่อนไขข้อมูลตกค้างจากระบบเดิม
            print(f"  [MIGRATE] ID: {car_app.id} | Creator: {creator_name} | Created: {created_str} | Destination: {car_app.location}")
            print(f"            Status: 'pending on director' -> 'pending on header'")

            if not dry_run:
                car_app.status = "pending on header"
                car_app.save()

            migrated_count += 1
        else:
            # คำขอที่ได้รับการจัดสรรรถ/คนขับจากพัสดุแล้ว หรือเป็นของระบบใหม่
            print(f"  [SKIP]    ID: {car_app.id} | Creator: {creator_name} | Already has approvals (admin={has_admin_approval}, header={has_header_approval})")
            skipped_count += 1

    print("-" * 70)
    if dry_run:
        print(f"[!] DRY RUN COMPLETE: {migrated_count} application(s) would be updated, {skipped_count} skipped.")
        print("[!] No changes were written to the database. Run without --dry-run to apply.")
    else:
        print(f"[OK] MIGRATION COMPLETE: Successfully updated {migrated_count} application(s), {skipped_count} skipped.")
    print("=" * 70)

    return migrated_count, skipped_count


def setup_app(config_file=None):
    app = Flask(__name__)
    if not config_file:
        config_file = os.environ.get(
            "KAMPAN_SETTINGS",
            os.path.join(os.path.dirname(__file__), "..", "kampan-development.cfg"),
        )

    if os.path.exists(config_file):
        app.config.from_pyfile(os.path.abspath(config_file))
        print(f"[*] Loaded configuration from: {config_file}")
    else:
        print(f"[!] Warning: Config file not found at {config_file}, using environment variables")

    models.init_mongoengine(app.config)
    return app


def main():
    parser = argparse.ArgumentParser(
        description="Migrate legacy out-of-town car applications to the new approval workflow."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the migration without modifying database records.",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to the Kampan configuration file (e.g. kampan-development.cfg).",
    )

    args = parser.parse_args()

    setup_app(args.config)
    migrate_car_applications(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
