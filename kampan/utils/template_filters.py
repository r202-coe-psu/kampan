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
