#!/usr/bin/env python3
"""
สร้างคำขอใช้รถ mock แล้วเดิน flow จริงเพื่อยิงแจ้งเตือนในระบบ (กระดิ่ง) ให้ลองดูบน dev

Usage:
    python scripts/seed_mock_notifications.py --email USER_EMAIL [--db kampandb]
    python scripts/seed_mock_notifications.py --clear [--db kampandb]

USER_EMAIL ต้องเป็นสมาชิก org ที่เปิดระบบจองรถ และเป็นหัวหน้าฝ่าย (head) + ผู้จัดรถ (dispatcher)
คำขอที่สร้างมี request_reason ขึ้นต้นด้วย "[mock-noti]" ส่วน --clear ลบเฉพาะคำขอเหล่านั้นและแจ้งเตือนของมัน
ไม่ส่งอีเมล (เรียกเฉพาะ notify_in_app)
"""

import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402

from kampan import models  # noqa: E402
from kampan.utils import car_reservation_email, car_reservation_flow as flow  # noqa: E402
from kampan.web import acl, views  # noqa: E402

MARK = "[mock-noti]"
MOCK_REQUESTER_EMAIL = "noti-requester@mock.kampan.local"


def make_app(db):
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "kampan", "web")
    app = Flask("kampan.web", template_folder=os.path.join(root, "templates"))
    app.config["SECRET_KEY"] = "seed"
    app.config["SERVER_NAME"] = "localhost:8081"
    app.config["MONGODB_SETTINGS"] = {"db": db, "host": "localhost"}
    models.init_db(app)
    acl.init_acl(app)
    views.register_blueprint(app)
    return app


def mock_requester(org, division, added_by):
    user = models.User.objects(email=MOCK_REQUESTER_EMAIL).first()
    if user is None:
        user = models.User(
            first_name="ผู้ขอทดสอบ",
            last_name="แจ้งเตือน",
            email=MOCK_REQUESTER_EMAIL,
            username="noti_requester_mock",
        ).save()
    if not models.OrganizationUserRole.objects(organization=org, user=user).first():
        models.OrganizationUserRole(
            organization=org,
            user=user,
            division=division,
            roles=["staff"],
            status="active",
            added_by=added_by,
            last_modifier=added_by,
        ).save()
    return user


def new_request(org, division, creator, days_ahead, location):
    departure = datetime.datetime.combine(
        datetime.date.today() + datetime.timedelta(days=days_ahead), datetime.time(8)
    )
    return models.CarReservation(
        organization=org,
        division=division,
        creator=creator,
        location=location,
        request_reason=f"{MARK} ประชุมที่{location}",
        departure_datetime=departure,
        return_datetime=departure + datetime.timedelta(hours=9),
        passenger_number=3,
        request_type="domestic",
        province_scope="in_province",
        details=models.car_reservations.DomesticDetails(
            vehicle_kind="ตู้", vehicle_count=1, district="หาดใหญ่", province="สงขลา"
        ),
    )


def seed(email):
    me = models.User.objects(email=email).first()
    if me is None:
        sys.exit(f"ไม่พบผู้ใช้ {email}")
    org = models.Organization.objects(enabled_modules="car_reservation").first()
    my_role = models.OrganizationUserRole.objects(organization=org, user=me, status="active").first()
    if my_role is None or my_role.division is None:
        sys.exit(f"{email} ไม่ได้อยู่ในฝ่ายของ {org.name}")
    division = my_role.division
    requester = mock_requester(org, division, me)
    cars = list(flow.assignable_cars(org))
    drivers = [d for d in flow.assignable_drivers(org) if d != me] or list(flow.assignable_drivers(org))
    if not cars or not drivers:
        sys.exit("org นี้ยังไม่มีรถหรือพนักงานขับรถที่จัดได้")

    def notify(res, event, actor):
        car_reservation_email.notify_in_app(res, event, actor)
        print(f"  {event:<16} {res.location}")

    # 1) ผู้ขอยื่น -> หัวหน้าฝ่าย (คุณ) ได้ "submitted"
    r1 = new_request(org, division, requester, 20, "หอประชุมใหญ่")
    flow.submit(r1, requester)
    notify(r1, "submitted", requester)

    # 2) ยื่น + คุณอนุมัติขั้นหัวหน้า -> ขั้นผู้จัดรถคือคุณ จึงได้ "approved" จากผู้ขอ (แจ้งในนามผู้ขอ)
    r2 = new_request(org, division, requester, 22, "สนามบินหาดใหญ่")
    flow.submit(r2, requester)
    flow.approve(r2, me, comment="")
    notify(r2, "approved", requester)

    # 3) เดินครบเส้นทางจน active แล้วผู้ขอขอยกเลิก -> ผู้จัดรถ (คุณ) ได้ "cancel_requested"
    r3 = new_request(org, division, requester, 25, "ศาลากลางจังหวัดสงขลา")
    flow.submit(r3, requester)
    while r3.status == "pending":
        if flow.current_step_key(r3) == "dispatcher":
            flow.approve(r3, me, comment="", car=cars[0], driver=drivers[0])
        else:
            flow.approve(r3, me, comment="")
    flow.cancel(r3, requester, reason="เลื่อนกำหนดการ")
    notify(r3, r3.status, requester)

    # 4) คำขอของคุณเอง: ผู้ขอทดสอบไม่มีสิทธิ์อนุมัติ จึงแจ้งในนามผู้ขอทดสอบ
    r4 = new_request(org, division, me, 27, "มหาวิทยาลัยทักษิณ")
    flow.submit(r4, me)
    r4.status = "denied"
    r4.save()
    notify(r4, "denied", requester)

    r5 = new_request(org, division, me, 29, "โรงพยาบาลสงขลานครินทร์")
    flow.submit(r5, me)
    r5.status = "active"
    r5.car, r5.driver = cars[-1], drivers[0]
    r5.save()
    notify(r5, "active", requester)
    notify(r5, "completed", requester)

    print(f"แจ้งเตือนยังไม่อ่านของ {email}:", models.Notification.objects(user=me, organization=org, read_at=None).count())


def clear():
    reservations = models.CarReservation.objects(request_reason__startswith=MARK)
    ids = [r.id for r in reservations]
    deleted = sum(
        1 for n in models.Notification.objects(module="car_reservation")
        if n.ref is not None and n.ref.id in ids and n.delete() is None
    )
    print(f"ลบแจ้งเตือน {deleted} รายการ คำขอ {reservations.delete()} รายการ")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--email")
    parser.add_argument("--db", default="kampandb")
    parser.add_argument("--clear", action="store_true")
    args = parser.parse_args()
    app = make_app(args.db)
    with app.test_request_context():
        if args.clear:
            clear()
        elif args.email:
            seed(args.email)
        else:
            parser.error("ต้องระบุ --email หรือ --clear")


if __name__ == "__main__":
    main()
