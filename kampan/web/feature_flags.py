from functools import wraps

from flask import abort, current_app

# ปิด/เปิดระบบขอซื้อขอจ้าง (Requisition, Requisition Timeline) และแหล่งเงิน (MAS)
# web app ไม่ได้โหลด default_settings.py ค่าที่ไม่ได้ตั้งไว้จึงต้องหมายถึงปิด
PROCUREMENT_REQUISITION_ENABLED = "PROCUREMENT_REQUISITION_ENABLED"


TRUE_VALUES = {"1", "true", "yes", "on"}


def is_requisition_enabled() -> bool:
    """ค่าจาก env / ไฟล์ .cfg เป็น string เสมอ ("False" ก็ truthy) จึงต้องแปลงเองก่อนใช้"""
    value = current_app.config.get(PROCUREMENT_REQUISITION_ENABLED, False)
    if isinstance(value, str):
        return value.strip().lower() in TRUE_VALUES
    return bool(value)


def abort_if_requisition_disabled() -> None:
    """ตอบ 404 เมื่อปิดระบบขอซื้อขอจ้าง · ใช้เป็น before_request ของ blueprint ที่ทั้งก้อนเป็นขอซื้อขอจ้าง"""
    if not is_requisition_enabled():
        abort(404)


def requisition_required(func):
    """decorator สำหรับ route ขอซื้อขอจ้างที่อยู่ปนใน blueprint เดียวกับหน้า MA"""

    @wraps(func)
    def wrapped(*args, **kwargs):
        abort_if_requisition_disabled()
        return func(*args, **kwargs)

    return wrapped
