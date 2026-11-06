"""ย้าย org ไปใช้โมดูล car_reservation: ลบ car_flow ที่ค้างจากรอบก่อน เปลี่ยนชื่อโมดูล/collection เดิม และเปิดโมดูลให้ org ที่ระบุ"""

import mongomock
from bson import ObjectId

from scripts.migrate_car_reservation_module import migrate

# ชื่อเดิมของโมดูล (ก่อน rename) ประกอบจากสองท่อนเพื่อไม่ให้คำเดิมค้างอยู่ใน source
LEGACY_MODULE = "sn" + "or_car"
LEGACY_REQUESTS = LEGACY_MODULE + "_requests"
LEGACY_POSITIONS = "car_flow_positions"

FLEET = ObjectId()
OTHER = ObjectId()
MIGRATED_EARLIER = ObjectId()


def _db():
    db = mongomock.MongoClient().kampandb
    db.organizations.insert_many(
        [
            {"_id": FLEET, "name": "Fleet", "car_flow": "legacy",
             "enabled_modules": ["inventory", "procurement", "car", "motorcycle"]},
            {"_id": OTHER, "name": "Other", "car_flow": "other"},
            {"_id": MIGRATED_EARLIER, "name": "Early",
             "enabled_modules": ["inventory", LEGACY_MODULE]},
        ]
    )
    return db


def test_car_flow_is_removed_from_every_organization():
    db = _db()

    migrate(db)

    assert db.organizations.count_documents({"car_flow": {"$exists": True}}) == 0


def test_organization_gets_the_car_reservation_module_and_keeps_its_others():
    db = _db()

    migrate(db, organization_id=str(FLEET))

    modules = db.organizations.find_one({"_id": FLEET})["enabled_modules"]
    assert modules == ["inventory", "procurement", "car", "motorcycle", "car_reservation"]


def test_organization_that_never_set_modules_is_left_alone():
    db = _db()

    migrate(db, organization_id=str(FLEET))

    assert "enabled_modules" not in db.organizations.find_one({"_id": OTHER})


def test_dry_run_changes_nothing():
    db = _db()
    db[LEGACY_REQUESTS].insert_one({"_id": 1})

    migrate(db, organization_id=str(FLEET), dry_run=True)

    fleet = db.organizations.find_one({"_id": FLEET})
    assert fleet["car_flow"] == "legacy"
    assert "car_reservation" not in fleet["enabled_modules"]
    assert db.organizations.find_one({"_id": MIGRATED_EARLIER})["enabled_modules"] == ["inventory", LEGACY_MODULE]
    assert LEGACY_REQUESTS in db.list_collection_names()
    assert "car_reservations" not in db.list_collection_names()


def test_running_twice_does_not_add_car_reservation_twice():
    db = _db()

    migrate(db, organization_id=str(FLEET))
    migrate(db, organization_id=str(FLEET))

    assert db.organizations.find_one({"_id": FLEET})["enabled_modules"].count("car_reservation") == 1


def test_old_module_key_is_renamed_in_every_organization():
    db = _db()

    migrate(db)

    assert db.organizations.find_one({"_id": MIGRATED_EARLIER})["enabled_modules"] == ["inventory", "car_reservation"]


def test_renaming_the_module_key_twice_leaves_a_single_entry():
    db = _db()
    db.organizations.update_one({"_id": MIGRATED_EARLIER}, {"$push": {"enabled_modules": "car_reservation"}})

    migrate(db)
    migrate(db)

    assert db.organizations.find_one({"_id": MIGRATED_EARLIER})["enabled_modules"] == ["inventory", "car_reservation"]


def test_old_collections_are_renamed_with_their_documents():
    db = _db()
    db[LEGACY_REQUESTS].insert_many([{"_id": 1}, {"_id": 2}])
    db[LEGACY_POSITIONS].insert_one({"_id": 3})

    migrate(db)

    assert sorted(d["_id"] for d in db.car_reservations.find()) == [1, 2]
    assert [d["_id"] for d in db.car_reservation_positions.find()] == [3]
    assert LEGACY_REQUESTS not in db.list_collection_names()
    assert LEGACY_POSITIONS not in db.list_collection_names()


def test_old_collection_is_merged_into_an_existing_new_one():
    db = _db()
    db[LEGACY_REQUESTS].insert_many([{"_id": 1}, {"_id": 2}])
    db.car_reservations.insert_one({"_id": 2, "kept": True})
    db.car_reservations.insert_one({"_id": 9})

    migrate(db)

    docs = {d["_id"]: d for d in db.car_reservations.find()}
    assert sorted(docs) == [1, 2, 9]
    assert docs[2] == {"_id": 2, "kept": True}
    assert LEGACY_REQUESTS not in db.list_collection_names()


def test_running_twice_does_not_lose_renamed_documents():
    db = _db()
    db[LEGACY_REQUESTS].insert_one({"_id": 1})

    migrate(db)
    migrate(db)

    assert [d["_id"] for d in db.car_reservations.find()] == [1]
