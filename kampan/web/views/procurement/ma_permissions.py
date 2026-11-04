"""สิทธิ์ของระบบ MA ที่ใช้ร่วมกันทุกหน้า

- ``edit_checker`` / ``can_edit_procurement``: กติกา "ผู้แก้ไข MA ได้" ใช้กับแก้ไข, ต่ออายุ, ไม่ต่ออายุ,
  บันทึกจ่ายงวด และเพิ่ม log การแจ้งเตือนเอง (admin ของหน่วยงาน, ผู้สร้าง MA หรือผู้รับผิดชอบรายการย่อยใดก็ได้)
- ``visible_procurements``: MA ที่ผู้ใช้เห็นในหน้ารายการ (#31 จะเปลี่ยนกติกาที่ฟังก์ชันนี้ที่เดียว)

ทุกฟังก์ชันรับ organization ที่ ACL ตรวจสมาชิกภาพแล้ว (g.organization) ไม่รับจาก input
"""

from collections.abc import Callable

from flask_login import current_user

from kampan import models
from kampan.models.procurement import procurement_ids_of


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
        if _reference_id(procurement, "created_by") == user.id:
            return True
        if member_id is None:
            return False
        return any(member_id in item.get_responsible_ids() for item in procurement.get_items())

    return _can_edit


def can_edit_procurement(procurement, organization, user=None) -> bool:
    return edit_checker(organization, user)(procurement)


def visible_procurements(organization, user=None):
    """queryset ของ MA ที่ผู้ใช้เห็นในหน้ารายการ (คงพฤติกรรมเดิม แต่คิดจากรายการย่อย)

    - admin / manager: เห็นทั้งหน่วยงาน
    - head: เห็น MA ที่มีรายการย่อยซึ่งฝ่ายของตัวเองรับผิดชอบ
    - staff: เห็น MA ที่ตัวเองเป็นผู้รับผิดชอบรายการย่อยอย่างน้อย 1 รายการ
    - role อื่นเห็นทั้งหน่วยงานเหมือนเดิม
    """
    user = _resolve_user(user)
    procurements = models.Procurement.objects(organization=organization)

    def has_role(*roles):
        return user.has_organization_roles(*roles, organization=organization)

    if has_role("admin", "manager"):
        return procurements

    member = get_member(organization, user)
    if not member:
        return procurements

    items = models.ProcurementItem.objects(organization=organization)
    if has_role("head") and member.division:
        return procurements.filter(id__in=procurement_ids_of(items.filter(responsible_divisions=member.division)))
    if has_role("head", "staff"):
        return procurements.filter(id__in=procurement_ids_of(items.filter(responsible_by=member)))
    return procurements
