#!/usr/bin/env python3
"""
Seed car form template (POC) ให้ organization

ตัวอย่าง:
    python scripts/seed_car_form_templates_poc.py --organization <id> --template physical_domestic --approver-user <user_id>
    python scripts/seed_car_form_templates_poc.py --organization <id> --template diis_general

- รันซ้ำได้ (idempotent): ถ้ามี template ชื่อเดียวกันใน organization แล้ว จะไม่สร้างซ้ำ
- physical_domestic: ถ้าไม่ระบุ --approver-user ขั้น "ผู้อนุมัติ" จะ fallback เป็น role endorser
"""

import argparse
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from flask import Flask

from kampan import models
from kampan.utils import car_form_seeds


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
    parser = argparse.ArgumentParser(description="Seed car form templates for the POC.")
    parser.add_argument("--organization", required=True, help="Organization id")
    parser.add_argument(
        "--template",
        required=True,
        choices=sorted(car_form_seeds.TEMPLATE_KEYS),
        help="Template key to seed",
    )
    parser.add_argument(
        "--approver-user",
        default=None,
        help="User id ของผู้อนุมัติ (ใช้กับ physical_domestic)",
    )
    parser.add_argument("--config", default=None, help="Path to the Kampan configuration file.")
    args = parser.parse_args()

    setup_app(args.config)

    organization = models.Organization.objects.get(id=args.organization)
    approver_user = models.User.objects.get(id=args.approver_user) if args.approver_user else None

    if args.template == "physical_domestic" and approver_user is None:
        print("[!] ไม่ได้ระบุ --approver-user: ขั้น 'ผู้อนุมัติ' ใช้ role endorser แทน")

    template = car_form_seeds.seed_template(
        organization, args.template, approver_user=approver_user
    )
    print(f"[OK] Template '{template.name}' id={template.id} (organization={organization.name})")


if __name__ == "__main__":
    main()
