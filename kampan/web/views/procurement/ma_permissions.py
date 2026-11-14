"""สิทธิ์ของระบบ MA ที่ใช้ร่วมกันทุกหน้า

- ``edit_checker`` / ``can_edit_procurement``: กติกา "ผู้แก้ไข MA ได้" ใช้กับแก้ไข,
  บันทึกจ่ายงวด และเพิ่ม log การแจ้งเตือนเอง (admin ของหน่วยงาน, ผู้สร้าง MA หรือผู้รับผิดชอบรายการย่อยใดก็ได้)
  ส่วนขอต่ออายุ (``can_request_renewal``: ผู้รับผิดชอบเท่านั้น) และอนุมัติ (``can_approve_renewal``: admin) แยกต่างหาก
- ``visible_procurements``: MA ที่ผู้ใช้มองเห็น (#31) ใช้กับทุกหน้าที่แสดง MA
- ``get_visible_procurement_or_404``: MA ตัวเดียวสำหรับหน้ารายละเอียด / หน้าที่ทำงานกับ MA ตัวเดียว

ทุกฟังก์ชันรับ organization ที่ ACL ตรวจสมาชิกภาพแล้ว (g.organization) ไม่รับจาก input
"""

from collections.abc import Callable

from bson import ObjectId
from flask import abort
from flask_login import current_user
from mongoengine.queryset.visitor import Q

from kampan import models
from kampan.models.procurement import procurement_ids_of

# role ที่เห็น MA ทั้งหน่วยงาน (มี role ใดในนี้ก็พอ แม้จะมี staff ด้วย)
# สถานะที่ admin ยืนยันแล้ว
CONFIRMED_STATUSES = ("renewed", "disactive")
WHOLE_ORGANIZATION_ROLES = ("admin", "head", "manager", "supervisor supplier", "director")


def _reference_id(document, field_name):
    value = document._data.get(field_name)
    return getattr(value, "id", value)


def _resolve_user(user):
    if user is None:
        return current_user._get_current_object()
    return user


def get_member(organization, user=None):
    """OrganizationUserRole ที่ active ของผู้ใช้ในหน่วยงานนี้"""
    user = _resolve_user(user)
    if not organization or not getattr(user, "is_authenticated", False):
        return None
    return models.OrganizationUserRole.objects(user=user, organization=organization, status="active").first()


def edit_checker(organization, user=None) -> Callable[[models.Procurement], bool]:
    """คืนฟังก์ชันตรวจว่าแก้ MA ได้ไหม (ค้นหา role/สมาชิกครั้งเดียว ใช้ซ้ำได้ทั้งหน้ารายการ)"""
    user = _resolve_user(user)
    if not organization or not getattr(user, "is_authenticated", False):
        return lambda procurement: False

    if user.has_organization_roles("admin", organization=organization):
        return lambda procurement: True

    member = get_member(organization, user)
    member_id = member.id if member else None

    def _can_edit(procurement) -> bool:
        if _reference_id(procurement, "organization") != organization.id:
            return False
        # admin ยืนยันแล้ว (ต่ออายุแล้ว / ไม่ต่ออายุ) ผู้รับผิดชอบและผู้สร้างแก้อะไรไม่ได้อีก
        if procurement.status in CONFIRMED_STATUSES:
            return False
        if _reference_id(procurement, "created_by") == user.id:
            return True
        if member_id is None:
            return False
        return any(member_id in item.get_responsible_ids() for item in procurement.get_items())

    return _can_edit


def can_edit_procurement(procurement, organization, user=None) -> bool:
    return edit_checker(organization, user)(procurement)


def can_request_renewal(procurement, organization, user=None) -> bool:
    """ผู้รับผิดชอบรายการย่อยของ MA นี้เท่านั้นที่กดขอต่ออายุ / ไม่ต่ออายุได้ (ผู้สร้าง, admin, คนอื่นที่แก้ได้ไม่ใช่)
    และต้องเป็นสถานะรอตรวจสอบหรือรอต่ออายุ ไม่ใช่แบบร่าง / ต่ออายุแล้ว / ไม่ต่ออายุ / สัญญาหลักที่แยกสัญญาย่อย
    (อ้างอิงอย่างเดียว)"""
    # รอตรวจสอบ (ขอครั้งแรก) หรือรอต่ออายุ (เปลี่ยนคำขอ ต่ออายุ <-> ไม่ต่ออายุ ได้จนกว่า admin จะอนุมัติ)
    if (
        not organization
        or procurement.get_renewal_status() not in ("review", "renewal-requested")
        or procurement.is_renewed()
    ):
        return False
    if _reference_id(procurement, "organization") != organization.id or procurement.has_child_procurements():
        return False
    member = get_member(organization, user)
    if member is None:
        return False
    return any(member.id in item.get_responsible_ids() for item in procurement.get_items())


def can_approve_renewal(organization, user=None) -> bool:
    """ผู้อนุมัติการต่ออายุ / ไม่ต่ออายุ: admin ของหน่วยงาน (รวม global admin)"""
    user = _resolve_user(user)
    if not organization or not getattr(user, "is_authenticated", False):
        return False
    return user.has_organization_roles("admin", organization=organization)


def renewal_requested_as(procurement, request_value: str) -> bool:
    """MA อยู่ในสถานะ "รอต่ออายุ" และสิ่งที่ผู้รับผิดชอบขอตรงกับ ``request_value`` (renew / stop)
    และไม่ใช่สัญญาหลักที่แยกสัญญาย่อย (อ้างอิงอย่างเดียว) · admin ข้ามขั้นตอนขอไม่ได้"""
    return (
        procurement.status == "renewal-requested"
        and procurement.renewal_request == request_value
        and not procurement.has_child_procurements()
    )


def _sees_whole_organization(user, member) -> bool:
    if "admin" in (user.roles or []):
        return True
    return bool(member and set(member.roles or []) & set(WHOLE_ORGANIZATION_ROLES))


def my_division_filter(organization, user=None):
    """ฝ่ายที่ใช้กับ checkbox "เฉพาะฝ่ายของฉัน" (เฉพาะกลุ่มเห็นทั้งหน่วยงานที่มีฝ่าย) ไม่มีคืน None"""
    user = _resolve_user(user)
    member = get_member(organization, user)
    if not member or not member.division or not _sees_whole_organization(user, member):
        return None
    return member.division


def visible_procurements(organization, user=None, only_my_division: bool = False):
    """queryset ของ MA ที่ผู้ใช้มองเห็น (#31) ใช้กับทุกหน้าที่แสดง MA ทั้งหน้ารายการและหน้ารายละเอียด

    - กลุ่มเห็นทั้งหน่วยงาน (admin, head, manager, supervisor supplier, director และ global admin):
      เห็นทุก MA ถ้า ``only_my_division`` เห็นเฉพาะ MA ที่มีรายการย่อยซึ่งฝ่ายของตัวเองรับผิดชอบ
    - role อื่น: เห็น MA ที่ตัวเองเป็นผู้รับผิดชอบรายการย่อยอย่างน้อย 1 รายการ หรือเป็นผู้สร้าง
      (ผู้แก้ไข MA ได้ต้องมองเห็น MA นั้นเสมอ) ``only_my_division`` ไม่มีผล
    - ไม่ใช่สมาชิกของหน่วยงาน: ไม่เห็นอะไรเลย
    """
    user = _resolve_user(user)
    procurements = models.Procurement.objects(organization=organization)
    if not organization or not getattr(user, "is_authenticated", False):
        return procurements.filter(id__in=[])

    member = get_member(organization, user)
    items = models.ProcurementItem.objects(organization=organization)
    if _sees_whole_organization(user, member):
        if only_my_division and member and member.division:
            return procurements.filter(id__in=procurement_ids_of(items.filter(responsible_divisions=member.division)))
        return procurements

    if not member:
        return procurements.filter(id__in=[])
    responsible_ids = procurement_ids_of(items.filter(responsible_by=member))
    return procurements.filter(Q(id__in=responsible_ids) | Q(created_by=user))


def get_visible_procurement_or_404(procurement_id, organization, user=None) -> models.Procurement:
    """MA ตัวเดียวที่ผู้ใช้มองเห็นในหน่วยงานนี้ ไม่พบ / หน่วยงานอื่น / มองไม่เห็น = 404 (ไม่ใช้ 403 เพราะ ACL แปลงเป็น redirect)"""
    if not organization or not ObjectId.is_valid(str(procurement_id)):
        abort(404)
    procurement = visible_procurements(organization, user).filter(id=procurement_id).first()
    if not procurement:
        abort(404)
    return procurement
