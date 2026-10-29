"""ตรวจขอบเขตของ module องค์กร และหา url_for ที่อ้าง endpoint ที่ไม่มีอยู่จริง

รัน: python scripts/check_module_boundaries.py  (exit 1 เมื่อพบปัญหา)
"""

import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
WEB = ROOT / "kampan" / "web"
TEMPLATES = WEB / "templates"
ORGANIZATION_TEMPLATES = TEMPLATES / "organizations"
ORGANIZATION_VIEWS = WEB / "views" / "organizations"

INVENTORY_BLUEPRINTS = {
    "approve_orders",
    "categories",
    "dashboard",
    "inventories",
    "item_checkouts",
    "item_orders",
    "item_positions",
    "item_registers",
    "items",
    "lost_breaks",
    "suppliers",
    "warehouses",
}

TEMPLATE_REFERENCE = re.compile(
    r"{%-?\s*(?:extends|include|import|from)\s+['\"]/?([\w-]+)/"
)
# endpoint ที่พังอยู่ก่อนแยก module องค์กร ยังไม่อยู่ใน scope ที่จะแก้
# ลบรายการออกเมื่อแก้แล้ว สคริปต์จะ fail ถ้ารายการไหนไม่พบในโค้ดแล้ว
KNOWN_BROKEN_ENDPOINTS = {
    (
        "kampan/web/templates/admin/dashboard/daily_dashboard.html",
        "dashboard.daily_dashboard",
    ),
    (
        "kampan/web/templates/admin/dashboard/index-admin.html",
        "admin.administration.classes.view",
    ),
    ("kampan/web/templates/admin/dashboard/index-admin.html", "classes.enroll"),
    ("kampan/web/templates/admin/organizations/index.html", "organizations.index"),
    ("kampan/web/templates/approve_orders/item_checkouts.html", "approve_orders.index"),
    (
        "kampan/web/templates/dashboard/daily_dashboard.html",
        "dashboard.daily_dashboard",
    ),
    (
        "kampan/web/templates/dashboard/daily_dashboard.html",
        "dashboard.monthly_dashboard",
    ),
    (
        "kampan/web/templates/dashboard/daily_dashboard.html",
        "dashboard.yearly_dashboard",
    ),
    ("kampan/web/templates/dashboard/index-admin.html", "administration.classes.view"),
    ("kampan/web/templates/dashboard/index-admin.html", "classes.enroll"),
    (
        "kampan/web/templates/dashboard/monthly_dashboard.html",
        "dashboard.daily_dashboard",
    ),
    (
        "kampan/web/templates/dashboard/monthly_dashboard.html",
        "dashboard.monthly_dashboard",
    ),
    (
        "kampan/web/templates/dashboard/monthly_dashboard.html",
        "dashboard.yearly_dashboard",
    ),
    (
        "kampan/web/templates/dashboard/yearly_dashboard.html",
        "dashboard.daily_dashboard",
    ),
    (
        "kampan/web/templates/dashboard/yearly_dashboard.html",
        "dashboard.monthly_dashboard",
    ),
    (
        "kampan/web/templates/dashboard/yearly_dashboard.html",
        "dashboard.yearly_dashboard",
    ),
    (
        "kampan/web/templates/procurement/macros/upload_table.html",
        "admin.procurement_files.download",
    ),
    (
        "kampan/web/templates/procurement/macros/upload_table.html",
        "admin.procurement_files.delete",
    ),
    ("kampan/web/views/accounts.py", "dashboard.daily_dashboard"),
    ("kampan/web/views/admin/inventories.py", "admin.item_registers.index"),
    ("kampan/web/views/dashboard.py", "dashboard.item_report_all"),
}

ENDPOINT_REFERENCE = re.compile(
    r"(?:url_for\(\s*|render_pagination\([^,()]+,\s*)['\"]([\w.]+)['\"]"
)


def load_endpoints():
    # get_subblueprints หา package จาก cwd จึงต้องรันจาก root ของ repo
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))

    import mongomock
    from flask import Flask

    from kampan import models
    from kampan.web import acl, views

    app = Flask("kampan.web", template_folder=str(TEMPLATES))
    app.config["SECRET_KEY"] = "check-module-boundaries"
    app.config["MONGODB_SETTINGS"] = {
        "db": "check_module_boundaries",
        "mongo_client_class": mongomock.MongoClient,
    }
    models.init_db(app)
    acl.init_acl(app)
    views.register_blueprint(app)
    return {rule.endpoint for rule in app.url_map.iter_rules()}


def source_files():
    for path in sorted(WEB.rglob("*")):
        if path.suffix in {".py", ".html"} and "node_modules" not in path.parts:
            yield path


def is_organization_file(path):
    return path.is_relative_to(ORGANIZATION_TEMPLATES) or path.is_relative_to(
        ORGANIZATION_VIEWS
    )


def is_commented(text, position):
    line_start = text.rfind("\n", 0, position) + 1
    return text[line_start:position].lstrip().startswith("#")


def check(endpoints):
    errors = []
    unused_known_broken = set(KNOWN_BROKEN_ENDPOINTS)
    for path in source_files():
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT)

        for match in TEMPLATE_REFERENCE.finditer(text):
            if (
                path.is_relative_to(ORGANIZATION_TEMPLATES)
                and match.group(1) in INVENTORY_BLUEPRINTS
            ):
                line = text.count("\n", 0, match.start()) + 1
                errors.append(
                    f"{relative}:{line}: organization template uses inventory template '{match.group(1)}/'"
                )

        for match in ENDPOINT_REFERENCE.finditer(text):
            endpoint = match.group(1)
            line = text.count("\n", 0, match.start()) + 1
            if endpoint.startswith(".") or is_commented(text, match.start()):
                continue
            if (str(relative), endpoint) in KNOWN_BROKEN_ENDPOINTS:
                unused_known_broken.discard((str(relative), endpoint))
            elif endpoint not in endpoints:
                errors.append(f"{relative}:{line}: unknown endpoint '{endpoint}'")
            elif (
                is_organization_file(path)
                and endpoint.split(".")[0] in INVENTORY_BLUEPRINTS
            ):
                errors.append(
                    f"{relative}:{line}: organization module links to inventory endpoint '{endpoint}'"
                )

    for path, endpoint in sorted(unused_known_broken):
        errors.append(
            f"{path}: '{endpoint}' is no longer referenced, remove it from KNOWN_BROKEN_ENDPOINTS"
        )
    return errors


def main():
    errors = check(load_endpoints())
    for error in errors:
        print(error)
    if errors:
        print(f"{len(errors)} module boundary violation(s)")
        return 1
    print("module boundaries OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
