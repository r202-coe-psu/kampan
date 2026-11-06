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
