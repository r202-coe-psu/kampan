"""ย้ายช่อง car/driver/ปิดงานเดี่ยวของคำขอใช้รถเข้า assignments (หนึ่งชุดต่อคำขอเดิม)"""

import datetime

import mongomock
import pytest
from bson import DBRef, ObjectId

from scripts.migrate_car_reservation_assignments import MOVED_FIELDS, migrate

# autouse fixtures ของ conftest ต้องมีการเชื่อมต่อฐานข้อมูลของ app ก่อน
pytestmark = pytest.mark.usefixtures("app")

ORG = ObjectId()
OTHER_ORG = ObjectId()
CAR = DBRef("cars", ObjectId())
DRIVER = DBRef("users", ObjectId())
CONFIRMER = DBRef("users", ObjectId())
PHOTO_IN = ObjectId()
PHOTO_OUT = ObjectId()
STARTED = datetime.datetime(2026, 1, 15, 8, 40)
COMPLETED = datetime.datetime(2026, 1, 15, 16, 10)

COMPLETED_TRIP = {
    "_id": 1,
    "organization": DBRef("organizations", ORG),
    "status": "completed",
    "location": "กรุงเทพฯ",
    "car": CAR,
    "driver": DRIVER,
    "is_overtime": True,
    "last_mileage": 10250,
    "last_mileage_before": 10000,
    "fuel_liters": 20.5,
    "expense_case": "fleet_card",
    "cost_baht": 1200.5,
    "started_at": STARTED,
    "completed_at": COMPLETED,
    "closed_ip": "10.0.0.5",
    "mileage_photo_out": PHOTO_OUT,
    "mileage_photo_in": PHOTO_IN,
    "mileage_photos_at": COMPLETED,
    "closed_off_campus": False,
    "close_confirmation": "disputed",
    "close_confirmed_by": CONFIRMER,
    "close_confirmed_at": COMPLETED + datetime.timedelta(days=1),
    "close_reported_end": COMPLETED + datetime.timedelta(hours=1),
    "close_dispute_note": "กลับช้ากว่านี้",
}
WAITING = {
    "_id": 2,
    "organization": DBRef("organizations", ORG),
    "status": "pending",
    "location": "เชียงใหม่",
    "is_overtime": False,
}
FOREIGN = {
    "_id": 3,
    "organization": DBRef("organizations", OTHER_ORG),
    "status": "active",
    "car": CAR,
    "driver": DRIVER,
}

OLD_INDEXES = [
    ["organization", "car", "status", "departure_datetime"],
    ["organization", "driver", "status", "departure_datetime"],
]
KEPT_INDEXES = [
    ["organization", "status", "departure_datetime"],
    ["organization", "creator", "created_date"],
]
DIRECTIONS = {"created_date": -1}


def _db():
    db = mongomock.MongoClient().kampandb
    db.car_reservations.insert_many([dict(COMPLETED_TRIP), dict(WAITING), dict(FOREIGN)])
    for names in OLD_INDEXES + KEPT_INDEXES:
        db.car_reservations.create_index([(name, DIRECTIONS.get(name, 1)) for name in names])
    return db


def _index_keys(db):
    return sorted(
        [key for key, _ in info["key"]]
        for name, info in db.car_reservations.index_information().items()
        if name != "_id_"
    )


def test_dry_run_changes_nothing():
    db = _db()
    before = list(db.car_reservations.find())
    indexes = _index_keys(db)
    logged = []

    migrate(db, dry_run=True, log=logged.append)

    assert list(db.car_reservations.find()) == before
    assert _index_keys(db) == indexes
    assert logged and all(line.startswith("[dry-run] ") for line in logged if "request" in line or "index" in line)


def test_a_completed_trip_becomes_one_assignment_with_every_close_field():
    db = _db()

    migrate(db)

    doc = db.car_reservations.find_one({"_id": 1})
    (assignment,) = doc["assignments"]
    assert isinstance(assignment["assignment_id"], ObjectId)
    for name in MOVED_FIELDS:
        assert assignment[name] == COMPLETED_TRIP[name], name
        assert name not in doc, name
    # ฟิลด์ที่ไม่เกี่ยวกับชุดอยู่ที่เดิม
    assert doc["status"] == "completed"
    assert doc["location"] == "กรุงเทพฯ"


def test_a_request_that_was_not_dispatched_yet_gets_an_empty_list_and_loses_the_old_fields():
    db = _db()

    migrate(db)

    doc = db.car_reservations.find_one({"_id": 2})
    assert doc["assignments"] == []
    assert "is_overtime" not in doc
    assert doc["location"] == "เชียงใหม่"


def test_migrated_requests_load_through_the_model(app):
    from kampan import models

    db = models.CarReservation._get_db()
    org = models.Organization(name="Migrated").save()
    car = models.vehicles.Car(license_plate="กก 1", organization=org, status="active").save()
    user = models.User(
        first_name="Drv", last_name="Test", email="drv@test.com", username="drv_test"
    ).save()
    db.car_reservations.insert_one(
        {
            "_id": ObjectId(),
            "organization": org.to_dbref(),
            "request_type": "domestic",
            "location": "x",
            "request_reason": "y",
            "status": "completed",
            "car": car.to_dbref(),
            "driver": user.to_dbref(),
            "last_mileage_before": 100,
            "last_mileage": 160,
            "completed_at": COMPLETED,
        }
    )

    from scripts.migrate_car_reservation_assignments import migrate as run

    run(db)

    (reservation,) = models.CarReservation.objects(organization=org)
    assignment = reservation.first_assignment
    assert assignment.car == car and assignment.driver == user
    assert assignment.distance_km == 60
    assert reservation.all_closed


def test_running_twice_is_a_no_op():
    db = _db()
    migrate(db)
    after_first = list(db.car_reservations.find())
    logged = []

    migrate(db, log=logged.append)

    assert list(db.car_reservations.find()) == after_first
    assert not any("request " in line for line in logged)
    assert len(after_first[0]["assignments"]) == 1


def test_the_old_car_and_driver_indexes_are_dropped_and_the_others_kept():
    db = _db()

    migrate(db)

    assert _index_keys(db) == sorted(KEPT_INDEXES)


def test_organization_scoping_leaves_the_other_organizations_requests_and_indexes_alone():
    db = _db()

    migrate(db, organization_id=str(ORG))

    assert "assignments" in db.car_reservations.find_one({"_id": 1})
    assert "assignments" in db.car_reservations.find_one({"_id": 2})
    foreign = db.car_reservations.find_one({"_id": 3})
    assert "assignments" not in foreign
    assert foreign["car"] == CAR and foreign["driver"] == DRIVER
    assert _index_keys(db) == sorted(OLD_INDEXES + KEPT_INDEXES)

    # ที่เหลือรันทีหลังได้ แล้วค่อยลบ index เก่า
    migrate(db, organization_id=str(OTHER_ORG))

    assert len(db.car_reservations.find_one({"_id": 3})["assignments"]) == 1
    assert _index_keys(db) == sorted(KEPT_INDEXES)


def test_a_missing_collection_is_not_an_error():
    migrate(mongomock.MongoClient().kampandb)
