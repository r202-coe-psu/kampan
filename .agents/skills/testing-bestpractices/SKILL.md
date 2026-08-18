---
name: testing-bestpractices
description: Guidelines and best practices for writing Unit, Integration, and Security tests in Kampan. Load this when creating or reviewing tests for Flask views, MongoEngine models, ACL permissions, and financial calculations.
---

# Testing Best Practices (Kampan)

Kampan relies on comprehensive testing to ensure multi-tenant security, financial precision, and regression stability.

---

## 1. Test Categories & Tools

- **Framework**: `pytest` or `unittest`
- **HTTP Client Testing**: Flask test client (`app.test_client()`)
- **Database Testing**: MongoEngine with a test MongoDB database or `mongomock`

---

## 2. Testing Multi-Tenant Scoping & Security

Multi-tenancy isolation is the most critical security boundary in Kampan. Always test cross-tenant access denial.

```python
def test_cannot_access_other_organization_item(client, user_org_a, item_org_b):
    """Ensure user from Org A cannot view or edit an item belonging to Org B."""
    login_user(client, user_org_a)
    response = client.get(f"/items/{item_org_b.id}/edit")
    assert response.status_code == 404  # or 403 Forbidden
```

---

## 3. Testing Financial Decimal Calculations

Ensure precision is preserved without floating-point inaccuracies.

```python
from decimal import Decimal

def test_financial_calculation_precision():
    item = models.Item(
        name="Test Item",
        price=Decimal("1234.56"),
        organization=org
    )
    item.save()
    
    reloaded = models.Item.objects(id=item.id).first()
    assert reloaded.price == Decimal("1234.56")
    assert isinstance(reloaded.price, Decimal)
```

---

## 4. Testing Form Validation & Edge Cases

Test both valid payloads and invalid/malicious edge cases:
- Missing required fields
- Invalid number ranges (e.g. negative budget amounts)
- Empty strings, excessively long strings
- Non-existent references (invalid category ID or warehouse ID)

---

## 5. Test Structure Guidelines

- **Arrange**: Set up test organizations, users, and documents.
- **Act**: Execute the route handler, controller method, or model operation.
- **Assert**: Check status codes, database state changes, and flash messages.
- **Clean**: Ensure test collections are cleaned up after test execution.
