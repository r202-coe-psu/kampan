import datetime

from kampan import models


def business_days_between(organization, start_date, end_date):
    """Count business days strictly after start_date up to and including end_date.

    Business days are Monday-Friday that are not in the organization's CarHoliday list.
    """
    if end_date <= start_date:
        return 0

    holidays = {
        h.date
        for h in models.CarHoliday.objects(
            organization=organization, date__gt=start_date, date__lte=end_date
        )
    }

    count = 0
    day = start_date + datetime.timedelta(days=1)
    while day <= end_date:
        if day.weekday() < 5 and day not in holidays:
            count += 1
        day += datetime.timedelta(days=1)
    return count


def nth_business_day_after(organization, start_date, n):
    """วันทำการที่ n หลัง start_date (business_days_between(start, วันนั้น) == n ครั้งแรก)"""
    if n <= 0:
        return start_date
    # วันหยุดยาวไม่น่าเกินช่วงนี้ ดึงครั้งเดียวพอ
    window_end = start_date + datetime.timedelta(days=n * 3 + 60)
    holidays = {
        h.date
        for h in models.CarHoliday.objects(
            organization=organization, date__gt=start_date, date__lte=window_end
        )
    }
    count = 0
    day = start_date
    while True:
        day += datetime.timedelta(days=1)
        if day.weekday() < 5 and day not in holidays:
            count += 1
            if count == n:
                return day


def all_days_off(organization, start_date, end_date):
    """True when every day from start_date to end_date (inclusive) is a Saturday, Sunday
    or one of the organization's CarHoliday dates."""
    holidays = {
        h.date
        for h in models.CarHoliday.objects(
            organization=organization, date__gte=start_date, date__lte=end_date
        )
    }
    day = start_date
    while day <= end_date:
        if day.weekday() < 5 and day not in holidays:
            return False
        day += datetime.timedelta(days=1)
    return True
