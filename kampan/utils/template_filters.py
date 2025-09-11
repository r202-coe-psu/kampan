from flask import url_for
import datetime


def static_url(filename: str):
    return add_date_url(url_for("static", filename=filename))


def add_date_url(url: str):
    now = datetime.datetime.now()
    return f'{url}?date={now.strftime("%Y%m%d")}'


def format_date(date: datetime.datetime, formatter: str = "%d/%m/%Y"):
    return date.strftime(formatter)


def format_number(data: str | int | float, digits: int = 2):
    if digits == 0:
        return f"{data:,.0f}"
    else:
        return f"{data:,.{digits}f}"


def format_thai_datetime_short_month(dt):
    if not isinstance(dt, datetime.datetime):
        return ""

    thai_year = dt.year + 543
    thai_months = {
        1: "ม.ค.",
        2: "ก.พ.",
        3: "มี.ค.",
        4: "ม.ย.",
        5: "พ.ค.",
        6: "มิ.ย.",
        7: "ก.ค.",
        8: "ส.ค.",
        9: "ก.ย.",
        10: "ต.ค.",
        11: "พ.ย.",
        12: "ธ.ค.",
    }
    thai_month = thai_months[dt.month]

    return f"{dt.day} {thai_month} {thai_year} {dt.hour:02}:{dt.minute:02} น."
