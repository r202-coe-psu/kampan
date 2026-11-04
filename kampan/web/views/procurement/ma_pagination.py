"""การแบ่งหน้าของหน้ารายการ MA (รายการ MA, รายการ MA ต่ออายุ, รายการไม่ต่ออายุ)

- ``page`` ที่น้อยกว่า 1 ใช้หน้าแรก มากกว่าจำนวนหน้าใช้หน้าสุดท้าย (ไม่ 404 เหมือน Pagination ของ flask-mongoengine)
- ``per_page`` จาก query string ถูกจำกัดไว้ที่ ``MAX_PER_PAGE`` กันการขอทีละมาก ๆ จนหน้าเว็บช้า
"""

from flask import request
from flask_mongoengine import Pagination
from mongoengine.queryset import QuerySet

MAX_PER_PAGE = 100


class ClampedPagination(Pagination):
    """Pagination ที่ clamp เลขหน้าแทน abort(404) และไม่ select_related ทั้งหน้า (ให้ view โหลดข้อมูลที่ใช้เอง)"""

    def __init__(self, iterable, page: int, per_page: int):
        self.iterable = iterable
        self.per_page = per_page
        is_queryset = isinstance(iterable, QuerySet)
        self.total = iterable.count() if is_queryset else len(iterable)
        self.page = min(max(page, 1), max(self.pages, 1))
        start = (self.page - 1) * per_page
        if is_queryset:
            self.items = iterable.skip(start).limit(per_page)
        else:
            self.items = iterable[start : start + per_page]


def paginate(iterable, default_per_page: int) -> ClampedPagination:
    """แบ่งหน้าตาม ``?page=`` / ``?per_page=`` ของ request (ค่าที่ไม่ใช่ตัวเลขใช้ค่าตั้งต้น)"""
    page = request.args.get("page", default=1, type=int)
    per_page = request.args.get("per_page", default=default_per_page, type=int)
    per_page = min(max(per_page, 1), MAX_PER_PAGE)
    return ClampedPagination(iterable, page, per_page)
