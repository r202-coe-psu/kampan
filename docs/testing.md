# Testing Guidelines & Rules (คู่มือและกฎการทดสอบระบบ Kampan)

เอกสารนี้ระบุกฎมาตรฐานและแนวทางการเขียนและรัน Automated Test ในโปรเจกต์ Kampan

---

## 🎯 กฎสำคัญ (Mandatory Rule)

> **ทุกครั้งหลังแก้ไขฟีเจอร์เดิม หรือเพิ่มฟีเจอร์ใหม่:**
> 1. **ต้องรัน Test เสมอ** (`poetry run pytest`) เพื่อยืนยันว่าไม่มีจุดไหนพัง (Zero Regression)
> 2. **สามารถนำไฟล์ Test เดิมมาต่อยอดหรือเพิ่มเคสใหม่ได้** (เช่น `tests/test_multi_org.py`, `tests/test_acl_organization.py`, `tests/test_procurement_views.py`) หรือสร้างไฟล์ทดสอบใหม่ภายใต้โฟลเดอร์ `tests/`
> 3. โค้ดทั้งหมดต้องผ่านการทดสอบ 100% ก่อนทำ commit/merge

---

## 🚀 วิธีรัน Test

```bash
# รันทุก test ทั้งหมดในโปรเจกต์
poetry run pytest

# รันเฉพาะไฟล์ที่ต้องการ
poetry run pytest tests/test_multi_org.py

# รันพร้อมดู output รายละเอียด
poetry run pytest -v -s
```

---

## 📁 โครงสร้างโฟลเดอร์ `tests/`

```
tests/
├── conftest.py                   # Pytest fixtures หลัก (app, clean_db, create_org, create_user, assign_user_to_org)
├── test_multi_org.py             # ทดสอบ User Organization Roles, Membership, และการ Switch Organization
├── test_acl_organization.py      # ทดสอบ ACL Resolution (g.organization) และ Decorator @organization_roles_required
└── test_procurement_views.py     # ทดสอบ Multi-Tenant Scoping และความปลอดภัยในการเข้าถึง Procurement ข้ามหน่วยงาน
```

---

## 🧰 Fixtures ที่มีให้ใช้งานใน `conftest.py`

| Fixture | การใช้งาน |
|---|---|
| `app` | Flask test application instance ที่ต่อกับ `mongomock` |
| `clean_db` | Autouse fixture ที่จะ drop collection ในฐานข้อมูลจำลองหลังแต่ละ test ทำงานเสร็จ |
| `create_org(name, status)` | Helper function สร้าง Organization document |
| `create_user(first_name, last_name, roles)` | Helper function สร้าง User document |
| `assign_user_to_org(user, org, roles, status)` | Helper function สร้าง OrganizationUserRole เพื่อผูก user เข้ากับ org |

---

## 💡 ตัวอย่างการเขียน Test

### 1. ทดสอบ Multi-Tenant Scoping & Security

```python
def test_procurement_cross_tenant_isolation(app, create_org, create_user, assign_user_to_org):
    with app.test_client() as client:
        with app.app_context():
            org_a = create_org("Org A")
            org_b = create_org("Org B")
            user_a = create_user("UserA", "MemberA")
            assign_user_to_org(user_a, org_a, roles=["staff"])

            # จำลอง Login ผ่าน session
            with client.session_transaction() as sess:
                sess["_user_id"] = str(user_a.id)
                sess["_fresh"] = True

            # เข้าถึงข้อมูลของ Org B ขณะที่ context เป็น Org A ต้องได้ 404
            response = client.get(f"/payment/{procurement_b.id}?organization_id={org_a.id}")
            assert response.status_code == 404
```

### 2. ทดสอบความแม่นยำของทศนิยม (DecimalField)

```python
from decimal import Decimal

def test_decimal_precision(app, create_org):
    with app.app_context():
        org = create_org("Org Test")
        # ทดสอบการบันทึกและการอ่านค่าทศนิยมทางการเงิน
        ...
```
