"""ย้าย org ไปใช้โมดูล snor_car: ลบ car_flow ที่ค้างจากรอบก่อน และเปิด snor_car ให้ org ที่ระบุ"""

import mongomock
from bson import ObjectId

from scripts.migrate_snor_car_module import migrate

SNOR = ObjectId()
DIIS = ObjectId()


def _db():
    db = mongomock.MongoClient().kampandb
    db.organizations.insert_many(
        [
            {"_id": SNOR, "name": "สนอ.", "car_flow": "snor",
             "enabled_modules": ["inventory", "procurement", "car", "motorcycle"]},
            {"_id": DIIS, "name": "DIIS", "car_flow": "diis"},
        ]
    )
    return db


def test_car_flow_is_removed_from_every_organization():
    db = _db()

    migrate(db)

    assert db.organizations.count_documents({"car_flow": {"$exists": True}}) == 0


def test_snor_organization_gets_the_snor_car_module_and_keeps_its_others():
    db = _db()

    migrate(db, snor_organization_id=str(SNOR))

    modules = db.organizations.find_one({"_id": SNOR})["enabled_modules"]
    assert modules == ["inventory", "procurement", "car", "motorcycle", "snor_car"]


def test_organization_that_never_set_modules_is_left_alone():
    db = _db()

    migrate(db, snor_organization_id=str(SNOR))

    assert "enabled_modules" not in db.organizations.find_one({"_id": DIIS})


def test_dry_run_changes_nothing():
    db = _db()

    migrate(db, snor_organization_id=str(SNOR), dry_run=True)

    snor = db.organizations.find_one({"_id": SNOR})
    assert snor["car_flow"] == "snor"
    assert "snor_car" not in snor["enabled_modules"]


def test_running_twice_does_not_add_snor_car_twice():
    db = _db()

    migrate(db, snor_organization_id=str(SNOR))
    migrate(db, snor_organization_id=str(SNOR))

    assert db.organizations.find_one({"_id": SNOR})["enabled_modules"].count("snor_car") == 1
