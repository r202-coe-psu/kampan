def _display_user(user):
    if not user:
        return ""
    return user.get_resources_fullname_th() or user.get_name()


def _search_text(car_application):
    creator = car_application.creator
    parts = [
        car_application.location,
        car_application.request_reason,
        car_application.car.license_plate if car_application.car else "",
        car_application.division.name if car_application.division else "",
        creator.first_name if creator else "",
        creator.last_name if creator else "",
        _display_user(creator),
        _display_user(car_application.driver),
    ]
    return " ".join(str(p) for p in parts if p).lower()


def search(car_applications, q=""):
    """กรองคำขอด้วยข้อความ: สถานที่ เหตุผล ทะเบียน ฝ่าย ผู้ขอ คนขับ"""
    q = (q or "").strip().lower()
    return [c for c in car_applications if not q or q in _search_text(c)]
