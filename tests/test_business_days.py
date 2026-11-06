"""business_days_between: นับวันทำการ (จ-ศ ที่ไม่ใช่วันหยุดของ org) หลัง start_date ถึง end_date"""

import datetime

from kampan import models
from kampan.utils import business_days

# ปฏิทินจริง: 2026-11-06 = ศุกร์, 11-09 = จันทร์, 11-11 = พุธ, 11-23 = จันทร์
FRIDAY = datetime.date(2026, 11, 6)
NEXT_MONDAY = datetime.date(2026, 11, 9)
NEXT_WEDNESDAY = datetime.date(2026, 11, 11)
MONDAY_AFTER_NEXT = datetime.date(2026, 11, 23)


def test_friday_to_next_wednesday_is_three_business_days(app, create_org):
    org = create_org("Org Alpha")
    assert business_days.business_days_between(org, FRIDAY, NEXT_WEDNESDAY) == 3


def test_friday_to_next_monday_is_one_business_day(app, create_org):
    org = create_org("Org Alpha")
    assert business_days.business_days_between(org, FRIDAY, NEXT_MONDAY) == 1


def test_org_holiday_is_not_counted(app, create_org):
    org = create_org("Org Alpha")
    models.CarHoliday(organization=org, date=NEXT_MONDAY, name="วันหยุด").save()
    assert business_days.business_days_between(org, FRIDAY, NEXT_WEDNESDAY) == 2


def test_holiday_of_another_org_is_ignored(app, create_org):
    org = create_org("Org Alpha")
    other = create_org("Org Beta")
    models.CarHoliday(organization=other, date=NEXT_MONDAY, name="วันหยุด").save()
    assert business_days.business_days_between(org, FRIDAY, NEXT_WEDNESDAY) == 3


def test_end_not_after_start_is_zero(app, create_org):
    org = create_org("Org Alpha")
    assert business_days.business_days_between(org, NEXT_WEDNESDAY, FRIDAY) == 0
    assert business_days.business_days_between(org, FRIDAY, FRIDAY) == 0


def test_two_weekends_span_is_ten_business_days(app, create_org):
    org = create_org("Org Alpha")
    assert business_days.business_days_between(org, NEXT_MONDAY, MONDAY_AFTER_NEXT) == 10
