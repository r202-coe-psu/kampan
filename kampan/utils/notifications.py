"""แจ้งเตือนในระบบ (กระดิ่งบน topbar) ใช้ร่วมกันได้ทุก module

ทุกฟังก์ชันรับ organization เสมอ ผู้ใช้เห็นเฉพาะแจ้งเตือนของ org ที่เลือกอยู่
"""

import datetime

from bson import ObjectId

from kampan import models


def send(organization, users, *, module, event, title, actor=None, ref=None, message="", url=""):
    """สร้างแจ้งเตือนหนึ่งรายการต่อผู้รับ ข้ามผู้รับซ้ำ ค่า None และคนที่ทำ action เอง"""
    recipients = []
    for user in users:
        if user is None or user == actor or user in recipients:
            continue
        recipients.append(user)
    for user in recipients:
        models.Notification(
            organization=organization,
            user=user,
            actor=actor,
            module=module,
            event=event,
            ref=ref,
            title=title,
            message=message,
            url=url,
        ).save()
    return recipients


def inbox(user, organization):
    return models.Notification.objects(user=user, organization=organization).order_by(
        "-created_date", "-id"
    )


def unread_count(user, organization):
    return inbox(user, organization).filter(read_at=None).count()


def find(user, organization, notification_id):
    """แจ้งเตือนของผู้ใช้คนนี้ใน org นี้เท่านั้น (ของคนอื่นได้ None)"""
    if not ObjectId.is_valid(notification_id):
        return None
    return inbox(user, organization).filter(id=notification_id).first()


def mark_read(notification):
    if notification.read_at is None:
        notification.read_at = datetime.datetime.now()
        notification.save()


def mark_all_read(user, organization):
    inbox(user, organization).filter(read_at=None).update(
        set__read_at=datetime.datetime.now()
    )
