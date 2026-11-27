from functools import wraps

from flask import abort, current_app

# ปิด/เปิดระบบขอซื้อขอจ้าง (Requisition, Requisition Timeline) และแหล่งเงิน (MAS)
# web app ไม่ได้โหลด default_settings.py ค่าที่ไม่ได้ตั้งไว้จึงต้องหมายถึงปิด
PROCUREMENT_REQUISITION_ENABLED = "PROCUREMENT_REQUISITION_ENABLED"
# ปิด/เปิดหน้าอัปโหลดไฟล์นำเข้า MA/MAS (/admin/upload_files) ค่าที่ไม่ได้ตั้งไว้หมายถึงปิด
PROCUREMENT_UPLOAD_FILES_ENABLED = "PROCUREMENT_UPLOAD_FILES_ENABLED"
# เปิดคู่มือเก่า (ครอบคลุม MAS / ขอซื้อขอจ้าง) แทนคู่มือ MA ใหม่ที่ /procurement/manuals ค่าที่ไม่ได้ตั้งไว้หมายถึงปิด
PROCUREMENT_LEGACY_MANUAL_ENABLED = "PROCUREMENT_LEGACY_MANUAL_ENABLED"


TRUE_VALUES = {"1", "true", "yes", "on"}


def _flag_enabled(name: str) -> bool:
    """ค่าจาก env / ไฟล์ .cfg เป็น string เสมอ ("False" ก็ truthy) จึงต้องแปลงเองก่อนใช้"""
    value = current_app.config.get(name, False)
    if isinstance(value, str):
        return value.strip().lower() in TRUE_VALUES
    return bool(value)


def is_requisition_enabled() -> bool:
    return _flag_enabled(PROCUREMENT_REQUISITION_ENABLED)


def is_upload_files_enabled() -> bool:
    return _flag_enabled(PROCUREMENT_UPLOAD_FILES_ENABLED)


def is_legacy_manual_enabled() -> bool:
    return _flag_enabled(PROCUREMENT_LEGACY_MANUAL_ENABLED)


def abort_if_upload_files_disabled() -> None:
    """ตอบ 404 เมื่อปิดหน้าอัปโหลดไฟล์ · ใช้เป็น before_request ของ blueprint upload_files"""
    if not is_upload_files_enabled():
        abort(404)


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
