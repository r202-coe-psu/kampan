---
name: testing-bestpractices
description: Guidelines and best practices for writing Unit, Integration, and Security tests in Kampan. Load this when creating or reviewing tests for Flask views, MongoEngine models, ACL permissions, and financial calculations.
---

# Testing Best Practices & Rules (Kampan)

Kampan relies on comprehensive automated testing to ensure multi-tenant security, financial precision, and regression stability.

---

## 📌 1. Mandatory Testing Rule

> ⚠️ **Rule:** ทุกครั้งที่มีการแก้ไข feature เดิม หรือพัฒนา feature ใหม่ **จะต้องรันเทสก่อนเสมอ** (`poetry run pytest`) เพื่อป้องกัน regression โดยสามารถนำไฟล์เทสเดิมใน `tests/` มาต่อยอดหรือเพิ่มเคสใหม่เข้าไปได้

---

## 🛠️ 2. Test Architecture & Tools

- **Framework**: `pytest` (config in `pytest.ini`)
- **Execution Command**:
  ```bash
  poetry run pytest
  # หรือรันเฉพาะไฟล์
  poetry run pytest tests/test_multi_org.py
  ```
- **HTTP Client Testing**: Flask test client (`app.test_client()`)
- **Database Testing**: `mongomock.MongoClient` (configured in `tests/conftest.py` with automatic per-test collection cleanup)

---

## 📂 3. Directory Structure & Existing Tests

```
tests/
├── conftest.py                   # Pytest fixtures (app, clean_db, create_org, create_user, assign_user_to_org)
├── test_multi_org.py             # User organization roles, membership, and switching
├── test_acl_organization.py      # ACL resolution and @organization_roles_required decorator
└── test_procurement_views.py     # Procurement multi-tenant scoping and cross-tenant isolation
```

---

## 🏢 4. Testing Multi-Tenant Scoping & Security

Multi-tenancy isolation is the most critical security boundary in Kampan. Always test cross-tenant access denial.

```python
def test_cannot_access_other_organization_item(app, create_org, create_user, assign_user_to_org):
    """Ensure user from Org A cannot view or edit an item belonging to Org B."""
    with app.test_client() as client:
        with app.app_context():
            org_a = create_org("Org A")
            org_b = create_org("Org B")
            user_a = create_user("UserA", "MemberA")
            assign_user_to_org(user_a, org_a, roles=["staff"])

            item_b = create_test_item(org_b)

            with client.session_transaction() as sess:
                sess["_user_id"] = str(user_a.id)
                sess["_fresh"] = True

            response = client.get(f"/items/{item_b.id}?organization_id={org_a.id}")
            assert response.status_code in (404, 403)
```

---

## 💰 5. Testing Financial Decimal Calculations

Ensure precision is preserved without floating-point inaccuracies.

```python
from decimal import Decimal

def test_financial_calculation_precision(app, create_org):
    with app.app_context():
        org = create_org("Finance Org")
        procurement = models.Procurement(
            name="Test Contract",
            company="Vendor",
            category="service",
            amount=Decimal("1234.56"),
            period=1,
            organization=org,
            start_date=datetime.datetime.now(),
            end_date=datetime.datetime.now() + datetime.timedelta(days=30),
        )
        procurement.save()
        
        reloaded = models.Procurement.objects(id=procurement.id).first()
        assert reloaded.amount == Decimal("1234.56")
        assert isinstance(reloaded.amount, Decimal)
```

---

## 📋 6. Test Development Checklist

- [ ] **Arrange**: ใช้ fixture เช่น `create_org`, `create_user`, `assign_user_to_org` ในการเตรียมข้อมูล
- [ ] **Act**: เรียก view function หรือ execute endpoint ผ่าน `client.get()` / `client.post()`
- [ ] **Assert**: ตรวจสอบ HTTP status code (404/403/302/200), response body หรือ database state
- [ ] **Clean**: Fixture `clean_db` ใน `conftest.py` จะล้างข้อมูลให้อัตโนมัติหลังจบแต่ละ test
