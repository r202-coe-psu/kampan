"""ล้างข้อมูล POC car form templates ออกจาก DB ให้ CarApplication โหลดได้บนโค้ดที่ไม่มี template แล้ว"""

import mongomock
from bson import ObjectId

from scripts.migrate_drop_car_form_poc import migrate


def _db():
    db = mongomock.MongoClient().kampandb
    org = ObjectId()
    template = ObjectId()
    db.car_form_templates.insert_one({"_id": template, "organization": org, "name": "ใบขอใช้รถ"})
    db.car_form_paper_files.insert_one({"organization": org})
    db.car_applications.insert_many(
        [
            {"_id": "from-template", "organization": org, "status": "pending",
             "form_template": template, "template_snapshot": {"steps": []}, "details": {"x": 1},
             "current_step": 0, "step_approvals": [], "audit_logs": [], "assigned_vehicle_type": "ตู้"},
            {"_id": "legacy", "organization": org, "status": "active", "using_type": "general",
             "current_step": 0, "step_approvals": [], "audit_logs": [], "details": {}},
        ]
    )
    return db


def test_requests_made_from_templates_move_to_an_archive_collection():
    db = _db()

    migrate(db)

    assert db.car_applications.find_one({"_id": "from-template"}) is None
    archived = db.car_applications_poc_archive.find_one({"_id": "from-template"})
    assert archived["form_template"] is not None


def test_legacy_requests_stay_and_lose_the_poc_fields():
    db = _db()

    migrate(db)

    legacy = db.car_applications.find_one({"_id": "legacy"})
    assert legacy["status"] == "active"
    for field in ("form_template", "template_snapshot", "details", "current_step",
                  "step_approvals", "audit_logs", "assigned_vehicle_type"):
        assert field not in legacy


def test_template_collections_are_renamed_to_archives():
    db = _db()

    migrate(db)

    names = db.list_collection_names()
    assert "car_form_templates" not in names
    assert "car_form_paper_files" not in names
    assert db.car_form_templates_poc_archive.count_documents({}) == 1
    assert db.car_form_paper_files_poc_archive.count_documents({}) == 1


def test_dry_run_changes_nothing():
    db = _db()

    migrate(db, dry_run=True)

    assert db.car_applications.count_documents({}) == 2
    assert db.car_applications.find_one({"_id": "legacy"})["current_step"] == 0
    assert "car_form_templates" in db.list_collection_names()


def test_running_twice_is_safe():
    db = _db()

    migrate(db)
    migrate(db)

    assert db.car_applications.count_documents({}) == 1
    assert db.car_applications_poc_archive.count_documents({}) == 1
    assert db.car_form_templates_poc_archive.count_documents({}) == 1
