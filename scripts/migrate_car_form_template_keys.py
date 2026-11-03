#!/usr/bin/env python3
"""
Migration: เปลี่ยน key ของฟิลด์ custom และขั้นอนุมัติใน car_form_templates เป็นรูปแบบสุ่ม
(f_xxxxxx / s_xxxxxx) พร้อมแก้ placements บน PDF ให้ตามไป

- ไม่แตะฟิลด์ catalog และไม่แตะ car_applications (คำขออ่านจาก template_snapshot ของตัวเอง)
- รันซ้ำได้: key ที่เป็นรูปแบบใหม่แล้วจะถูกข้าม
- spec: docs/specs/car_form_template_hidden_keys_2569-11-03_spec.md ข้อ 4
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import mongoengine as me

from kampan import models
from kampan.utils.car_form_keys import rekey_template


def migrate(dry_run):
    changed = skipped = failed = 0
    for template in models.car_form_templates.CarFormTemplate.objects():
        field_map, step_map = rekey_template(template)
        if not field_map and not step_map:
            skipped += 1
            continue
        print(f"[*] {template.name} ({template.id})")
        for old, new in {**field_map, **step_map}.items():
            print(f"      {old} -> {new}")
        if dry_run:
            template.validate()
            changed += 1
            continue
        try:
            template.save()
            changed += 1
        except me.ValidationError as error:
            failed += 1
            print(f"[!] ข้าม {template.name}: {error}")
    mode = "dry-run" if dry_run else "saved"
    print(f"[{mode}] changed={changed} skipped={skipped} failed={failed}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--db", default=os.environ.get("MONGODB_DB", "kampandb"))
    parser.add_argument("--host", default=os.environ.get("MONGODB_HOST", "localhost"))
    args = parser.parse_args()
    me.connect(db=args.db, host=args.host)
    migrate(args.dry_run)
