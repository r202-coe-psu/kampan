"""การแบ่งหน้าของหน้ารายการ MA (รายการ MA, รายการ MA ต่ออายุ, รายการไม่ต่ออายุ)

- ``page`` ที่น้อยกว่า 1 ใช้หน้าแรก มากกว่าจำนวนหน้าใช้หน้าสุดท้าย (ไม่ 404 เหมือน Pagination ของ flask-mongoengine)
- ``per_page`` จาก query string ถูกจำกัดไว้ที่ ``MAX_PER_PAGE`` กันการขอทีละมาก ๆ จนหน้าเว็บช้า
"""

from flask import request
from flask_mongoengine import Pagination
from mongoengine.queryset import QuerySet

from kampan.web.forms.procurement import SORT_OPTIONS

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


# ---------------------------------------------------------------------------
# การเรียงลำดับของหน้ารายการ MA (query string ``sort``)
# ---------------------------------------------------------------------------

SORT_KEYS = {key for key, _ in SORT_OPTIONS}
# ลำดับของ queryset (ตามหัวสัญญา) ``id`` ต่อท้ายให้ลำดับคงที่เมื่อค่าเท่ากัน
_QUERYSET_ORDER = {
    "created_desc": ("-created_date", "-id"),
    "created_asc": ("created_date", "id"),
    "name_asc": ("name", "id"),
}


def resolve_sort(default: str) -> str:
    """``?sort=`` ที่อยู่ใน whitelist ไม่เช่นนั้นใช้ค่าตั้งต้นของหน้า"""
    value = request.args.get("sort", "")
    return value if value in SORT_KEYS else default


def paginate_sorted(procurements, organization, sort: str, default_per_page: int):
    """แบ่งหน้า MA ตาม ``sort`` คืน (pagination, MA ของหน้านี้พร้อมรายการย่อยและผู้รับผิดชอบ)

    - สร้างก่อน-หลัง / ชื่อ: เรียงด้วย queryset แล้วโหลดเฉพาะหน้านั้น
    - วันหมดอายุ: เรียงจากวันสิ้นสุดของรายการย่อยที่หมดอายุก่อน ด้วย aggregation ครั้งเดียว (MA ที่ไม่มีรายการย่อยไว้ท้าย)
      แล้วโหลดเอกสารเฉพาะ MA ในหน้าที่แสดง
    """
    from kampan.models.procurement import (
        attach_items,
        procurement_ids_by_end_date,
        procurements_in_order,
    )

    if sort in _QUERYSET_ORDER:
        pagination = paginate(procurements.order_by(*_QUERYSET_ORDER[sort]), default_per_page)
        page_procurements = pagination.items
    else:
        ids = procurement_ids_by_end_date(
            procurements.order_by("-created_date", "-id"), organization, reverse=sort == "end_desc"
        )
        pagination = paginate(ids, default_per_page)
        page_procurements = procurements_in_order(pagination.items, organization)
    return pagination, attach_items(page_procurements, organization, with_responsibles=True)
