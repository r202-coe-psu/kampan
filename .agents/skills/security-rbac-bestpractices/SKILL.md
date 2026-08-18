---
name: security-rbac-bestpractices
description: Best practices for Multi-Tenancy security, Role-Based Access Control (RBAC), and ACL enforcement in Kampan. Load this when implementing routes, querying models, or auditing data protection.
---

# Security & RBAC Best Practices (Kampan)

Kampan serves multiple organizations (multi-tenant environment) and handles sensitive procurement, inventory, financial, and organizational data. Strict security boundaries are mandatory.

---

## 1. Multi-Tenant Organization Isolation

Data belonging to Organization A must **never** be accessible to Organization B.

### Rules:
1. **Never trust client-submitted `organization_id`** without validating that the authenticated user belongs to that organization.
2. Use `acl.py` helpers to resolve the viewing organization:
   ```python
   organization = acl.get_current_organization()  # or current_user.get_current_organization()
   ```
3. Always include `organization=organization` in every MongoEngine query when fetching, editing, or deleting documents.

```python
# ✅ SECURE: Scoped lookup
item = models.Item.objects(id=item_id, organization=organization).first()
if not item:
    return abort(404)

# ❌ INSECURE: IDOR vulnerability! Allows accessing items of any organization
item = models.Item.objects(id=item_id).first()
```

---

## 2. ACL & Role Protection (`kampan.web.acl`)

Every protected view must be annotated with appropriate authorization decorators.

### Available Decorators:

```python
from kampan.web import acl
from flask_login import login_required

# Requires user to be logged in
@login_required

# Requires user to have specific roles within the current organization
@acl.organization_roles_required("admin", "supervisor supplier")

# Requires system admin role
@acl.roles_required("admin")
```

### Checking Roles in Templates

```html
{% if current_user.has_organization_roles(g.organization, 'admin', 'supervisor supplier') %}
  <a href="{{ url_for('items.create') }}" class="btn btn-primary">เพิ่มพัสดุ</a>
{% endif %}
```

---

## 3. Form Security & CSRF Protection

1. Always use WTForms schemas for form submissions to ensure automatic CSRF protection and input sanitization.
2. Verify `request.method == "POST"` and `form.validate()` before taking mutating actions.
3. Never use raw `request.form.get()` without validation when updating database fields.

---

## 4. Session & Authentication Security

1. Passwords must never be stored in plain text. Always use Werkzeug's `generate_password_hash` / `check_password_hash`.
2. Do not expose sensitive user information (hashes, tokens, internal credentials) in API responses or templates.
3. When using OAuth2 / Authlib, ensure state tokens are properly verified to prevent CSRF in authentication flows.
