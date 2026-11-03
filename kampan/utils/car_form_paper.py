from jinja2 import ChainableUndefined
from jinja2.sandbox import SandboxedEnvironment

THAI_MONTHS = [
    "มกราคม",
    "กุมภาพันธ์",
    "มีนาคม",
    "เมษายน",
    "พฤษภาคม",
    "มิถุนายน",
    "กรกฎาคม",
    "สิงหาคม",
    "กันยายน",
    "ตุลาคม",
    "พฤศจิกายน",
    "ธันวาคม",
]

_env = SandboxedEnvironment(autoescape=True, undefined=ChainableUndefined)


def _thai_date(dt):
    return {"day": dt.day, "month_th": THAI_MONTHS[dt.month - 1], "year_be": dt.year + 543}


def _thai_datetime(dt):
    return {**_thai_date(dt), "time": dt.strftime("%H:%M")}


def _user_name(user):
    return user.get_resources_fullname_th() if user else ""


def _build_app(car_application):
    return {
        "requester_name": _user_name(car_application.creator),
        "division": car_application.division.name if car_application.division else "",
        "phone": car_application.phone,
        "location": car_application.location,
        "request_reason": car_application.request_reason,
        "passenger_number": car_application.passenger_number,
        "car_plate": (car_application.car.license_plate if car_application.car else "") or "",
        "driver_name": _user_name(car_application.driver),
        "departure": _thai_datetime(car_application.departure_datetime),
        "return": _thai_datetime(car_application.return_datetime),
        "created": _thai_date(car_application.created_date),
    }


def _build_approvals(car_application):
    approvals = {}
    for step in car_application.step_approvals:
        decided_at = step.decided_at
        approvals[step.step_key] = {
            "name": _user_name(step.decided_by),
            "date": decided_at.strftime("%d/%m/") + str(decided_at.year + 543) if decided_at else "",
            "decision": step.decision,
            "comment": step.comment,
        }
    return approvals


def render_paper(car_application):
    template = _env.from_string(car_application.template_snapshot.get("paper_html", ""))
    return template.render(
        app=_build_app(car_application),
        details=dict(car_application.details or {}),
        approvals=_build_approvals(car_application),
        org={"name": car_application.organization.name},
    )
