"""โมเดล CarAssignment: FileField ใน embedded document ใน list ใช้งานได้ และ helper ของ CarReservation"""

import datetime
import io

import pytest

from kampan import models
from kampan.models.car_reservations import required_vehicle_count

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


@pytest.fixture
def world(app, create_org, create_car, create_user):
    class World:
        pass

    w = World()
    w.org = create_org()
    w.cars = [create_car(w.org, "กก 1111"), create_car(w.org, "กก 2222")]
    w.drivers = [create_user("DriverA", "T"), create_user("DriverB", "T")]
    return w


def _reservation(world, assignments=(), **fields):
    fields.setdefault("request_type", "domestic")
    return models.CarReservation(
        organization=world.org,
        location="x",
        request_reason="y",
        departure_datetime=datetime.datetime(2026, 1, 15, 8, 0),
        return_datetime=datetime.datetime(2026, 1, 15, 17, 0),
        assignments=list(assignments),
        **fields,
    ).save()


def _two(world):
    return [
        models.CarAssignment(car=world.cars[0], driver=world.drivers[0]),
        models.CarAssignment(car=world.cars[1], driver=world.drivers[1]),
    ]


def test_a_file_in_an_embedded_assignment_is_written_and_read_back(world):
    reservation = _reservation(world, _two(world))

    second = reservation.assignments[1]
    second.mileage_photo_in.replace(io.BytesIO(PNG), filename="in.png", content_type="image/png")
    reservation.save()

    reloaded = models.CarReservation.objects.get(id=reservation.id)
    assert reloaded.assignments[0].mileage_photo_in.grid_id is None
    photo = reloaded.assignments[1].mileage_photo_in
    assert photo.read() == PNG
    assert photo.content_type == "image/png"
    assert photo.filename == "in.png"


def test_put_and_replace_on_a_loaded_embedded_assignment_work(world):
    reservation = _reservation(world, _two(world))
    loaded = models.CarReservation.objects.get(id=reservation.id)

    loaded.assignments[0].mileage_photo_out.put(
        io.BytesIO(PNG), filename="out.png", content_type="image/png"
    )
    loaded.save()
    again = models.CarReservation.objects.get(id=reservation.id)
    again.assignments[0].mileage_photo_out.replace(
        io.BytesIO(PNG + b"1"), filename="out2.png", content_type="image/png"
    )
    again.save()

    final = models.CarReservation.objects.get(id=reservation.id)
    assert final.assignments[0].mileage_photo_out.read() == PNG + b"1"
    assert final.assignments[0].mileage_photo_out.filename == "out2.png"
    assert final.assignments[1].mileage_photo_out.grid_id is None


def test_get_assignment_accepts_a_string_or_an_object_id_and_ignores_garbage(world):
    reservation = _reservation(world, _two(world))
    second = reservation.assignments[1]

    assert reservation.get_assignment(str(second.assignment_id)) is second
    assert reservation.get_assignment(second.assignment_id) is second
    assert reservation.get_assignment("not-an-id") is None
    assert reservation.get_assignment(None) is None
    assert reservation.get_assignment("0" * 24) is None


def test_reservation_helpers_summarise_the_assignments(world):
    empty = _reservation(world)
    assert empty.first_assignment is None
    assert empty.cars == [] and empty.drivers == []
    assert empty.has_overtime is False
    assert empty.all_closed is False

    reservation = _reservation(world, _two(world))
    assert reservation.first_assignment is reservation.assignments[0]
    assert reservation.cars == world.cars
    assert reservation.drivers == world.drivers

    reservation.assignments[1].is_overtime = True
    assert reservation.has_overtime is True

    reservation.assignments[0].completed_at = datetime.datetime.now()
    assert reservation.all_closed is False
    reservation.assignments[1].completed_at = datetime.datetime.now()
    assert reservation.all_closed is True


def test_assignment_distance_and_close_confirmation_status(app):
    now = datetime.datetime(2026, 1, 20, 12, 0)
    assignment = models.CarAssignment()
    assert assignment.is_closed is False
    assert assignment.distance_km is None
    assert assignment.close_confirmation_status(now) is None

    assignment.last_mileage_before, assignment.last_mileage = 100, 250
    assignment.completed_at = now - datetime.timedelta(days=1)
    assert assignment.distance_km == 150
    assert assignment.is_closed is True
    assert assignment.close_confirmation_status(now) == "pending"
    assignment.completed_at = now - datetime.timedelta(days=4)
    assert assignment.close_confirmation_status(now) == "auto_confirmed"
    assignment.close_confirmation = "disputed"
    assert assignment.close_confirmation_status(now) == "disputed"


def test_required_vehicle_count_follows_the_details_and_defaults_to_one(world):
    domestic = _reservation(
        world,
        details=models.car_reservations.DomesticDetails(
            vehicle_kind="ตู้", vehicle_count=3, district="a", province="b"
        ),
    )
    airport = _reservation(world, request_type="airport")

    assert required_vehicle_count(domestic) == 3
    assert required_vehicle_count(airport) == 1
    assert required_vehicle_count(models.CarReservation()) == 1


def test_the_indexes_cover_the_assignment_car_and_driver(app):
    fields = [
        [name for name, _ in spec["fields"]]
        for spec in models.CarReservation._meta["index_specs"]
    ]

    assert ["organization", "assignments.car", "status", "departure_datetime"] in fields
    assert ["organization", "assignments.driver", "status", "departure_datetime"] in fields
