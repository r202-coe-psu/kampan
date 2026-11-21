"""ย้าย org ไปใช้โมดูล car_reservation: ลบ car_flow ที่ค้างจากรอบก่อน เปลี่ยนชื่อโมดูล/collection เดิม และเปิดโมดูลให้ org ที่ระบุ"""

import mongomock
from bson import DBRef, ObjectId

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


def test_targeted_organization_that_never_set_modules_keeps_the_defaults_and_gets_car_reservation():
    db = _db()

    migrate(db, organization_id=str(OTHER))

    modules = db.organizations.find_one({"_id": OTHER})["enabled_modules"]
    assert modules == ["inventory", "procurement", "car", "motorcycle", "car_reservation"]


def test_the_scripts_default_modules_match_the_model():
    from kampan import models
    from scripts.migrate_car_reservation_module import DEFAULT_MODULES

    assert DEFAULT_MODULES == models.organizations.DEFAULT_MODULE_KEYS


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
    assert "car_reservation_positions" not in db.list_collection_names()
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
    # ฉบับเก่าที่ _id ชนไม่ถูกทิ้ง: เก็บไว้ทั้ง collection
    assert sorted(d["_id"] for d in db[LEGACY_REQUESTS + "_archive"].find()) == [1, 2]


def test_running_twice_does_not_lose_renamed_documents():
    db = _db()
    db[LEGACY_REQUESTS].insert_one({"_id": 1})

    migrate(db)
    migrate(db)

    assert [d["_id"] for d in db.car_reservations.find()] == [1]


# --- ตำแหน่งผู้อนุมัติเดิม (car_reservation_positions) -> organization role ---

ROLE_ORG = ObjectId()
HOLDER = ObjectId()
DELEGATE = ObjectId()
DRIVER = ObjectId()


def _ref(collection, oid):
    return DBRef(collection, oid)


def _positions_db():
    """org หนึ่งที่ตั้ง enabled_roles ไว้ มีผู้ดำรงตำแหน่ง/ผู้รักษาการ/คนขับรถ และตำแหน่งเดิมสองรายการ"""
    db = mongomock.MongoClient().kampandb
    db.organizations.insert_one(
        {"_id": ROLE_ORG, "name": "RoleOrg", "enabled_roles": ["staff", "admin"]}
    )
    for oid, roles in ((HOLDER, ["staff"]), (DELEGATE, ["staff", "admin"]), (DRIVER, ["driver"])):
        db.organization_user_roles.insert_one(
            {
                "organization": _ref("organizations", ROLE_ORG),
                "user": _ref("users", oid),
                "roles": roles,
                "status": "active",
            }
        )
    db.car_reservation_positions.insert_many(
        [
            {
                "organization": _ref("organizations", ROLE_ORG),
                "position_key": "dispatcher",
                "user": _ref("users", HOLDER),
                "delegates": [_ref("users", DELEGATE)],
            },
            {
                "organization": _ref("organizations", ROLE_ORG),
                "position_key": "president",
                "user": _ref("users", DRIVER),
                "delegates": [],
            },
        ]
    )
    return db


def _roles_of(db, oid):
    return db.organization_user_roles.find_one({"user": _ref("users", oid)})["roles"]


def test_position_holder_and_delegates_get_the_role_and_the_collection_is_archived():
    db = _positions_db()

    migrate(db)

    assert _roles_of(db, HOLDER) == ["staff", "dispatcher"]
    assert _roles_of(db, DELEGATE) == ["staff", "admin", "dispatcher"]
    assert "car_reservation_positions" not in db.list_collection_names()
    # คนที่ถูกข้าม (คนขับรถ ไม่ใช่สมาชิก active) ยังตามกลับได้จาก archive
    assert db.car_reservation_positions_archive.count_documents({}) == 2


def test_dry_run_reports_the_role_grants_when_only_the_oldest_positions_name_exists():
    db = _positions_db()
    db.car_reservation_positions.rename(LEGACY_POSITIONS)
    lines = []

    migrate(db, dry_run=True, log=lines.append)

    assert any("dispatcher: add role to user" in line for line in lines)
    assert _roles_of(db, HOLDER) == ["staff"]
    assert db[LEGACY_POSITIONS].count_documents({}) == 2


def test_a_driver_is_never_given_an_approval_role():
    db = _positions_db()

    migrate(db)

    assert _roles_of(db, DRIVER) == ["driver"]


def test_converted_role_is_added_to_the_organizations_enabled_roles():
    db = _positions_db()

    migrate(db)

    assert db.organizations.find_one({"_id": ROLE_ORG})["enabled_roles"] == [
        "staff",
        "admin",
        "dispatcher",
        "president",
    ]


def test_organization_without_enabled_roles_is_left_without_them():
    db = _positions_db()
    db.organizations.update_one({"_id": ROLE_ORG}, {"$unset": {"enabled_roles": ""}})

    migrate(db)

    assert "enabled_roles" not in db.organizations.find_one({"_id": ROLE_ORG})
    assert _roles_of(db, HOLDER) == ["staff", "dispatcher"]


def test_dry_run_converts_nothing_and_keeps_the_positions():
    db = _positions_db()

    migrate(db, dry_run=True)

    assert _roles_of(db, HOLDER) == ["staff"]
    assert db.organizations.find_one({"_id": ROLE_ORG})["enabled_roles"] == ["staff", "admin"]
    assert db.car_reservation_positions.count_documents({}) == 2


def test_running_the_position_conversion_twice_adds_each_role_once():
    db = _positions_db()

    migrate(db)
    migrate(db)

    assert _roles_of(db, HOLDER) == ["staff", "dispatcher"]
    assert db.organizations.find_one({"_id": ROLE_ORG})["enabled_roles"].count("dispatcher") == 1
