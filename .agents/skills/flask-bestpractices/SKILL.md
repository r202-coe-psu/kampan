---
name: flask-bestpractices
description: Best practices and guidelines for Flask application development in Kampan. Covers Blueprint routing, WTForms validation, Jinja2 templating, Redis RQ workers, error handling, and separation of concerns.
---

# Flask Best Practices (Kampan)

Kampan is a Python Flask web application. All Flask code must follow standard modular patterns, separation of concerns, and clean request lifecycle practices.

---

## 1. Blueprint Structure & Modular Routing

Every feature area must be encapsulated in its own Blueprint under `kampan/web/views/`.

### Blueprint Definition Pattern

```python
from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user
from kampan.web import forms, acl
from kampan import models, controllers

module = Blueprint("items", __name__, url_prefix="/items")
```

### Route Handler Guidelines

- **Guard Clauses First**: Validate user permissions, form submissions, and input parameters with early returns. The successful execution flow belongs at the end.
- **Explicit Status Codes & Redirects**: Always use `url_for` with the full blueprint endpoint (e.g. `url_for("items.index")` or `url_for(".index")`).
- **No Heavy Queries in Routes**: Route handlers should parse input, call controller/repository services, and pass results to templates.

```python
@module.route("/<item_id>/edit", methods=["GET", "POST"])
@login_required
@acl.organization_roles_required("admin", "supervisor supplier")
def edit(item_id: str):
    organization = acl.get_current_organization()
    item = models.Item.objects(id=item_id, organization=organization).first()
    if not item:
        return abort(404)

    form = forms.items.ItemForm(obj=item)
    if request.method == "POST" and form.validate():
        form.populate_obj(item)
        item.updated_by = current_user._get_current_object()
        item.updated_date = datetime.datetime.now()
        item.save()
        flash("บันทึกข้อมูลเรียบร้อยแล้ว", "success")
        return redirect(url_for("items.index"))

    return render_template("items/edit.html", form=form, item=item)
```

---

## 2. Form Handling & WTForms

Always use WTForms schemas located in `kampan/web/forms/` for processing and validating user inputs.

### Form Definition Guidelines

- Define forms matching specific actions (e.g. `ItemCreateForm`, `ItemSearchForm`, `RequisitionApprovalForm`).
- Use appropriate validators (`DataRequired`, `Length`, `NumberRange`, custom validators).
- Keep form field types aligned with MongoEngine model fields (e.g. `DecimalField`, `SelectField`, `StringField`).

```python
# kampan/web/forms/items.py
from wtforms import Form, fields, validators

class ItemForm(Form):
    name = fields.StringField(
        "ชื่อวัสดุ/อุปกรณ์",
        validators=[validators.DataRequired(message="กรุณากรอกชื่อวัสดุ/อุปกรณ์")],
    )
    price = fields.DecimalField(
        "ราคาต่อหน่วย",
        places=2,
        validators=[validators.DataRequired(), validators.NumberRange(min=0)],
    )
    status = fields.SelectField(
        "สถานะ",
        choices=[("active", "ใช้งาน"), ("inactive", "ระงับการใช้งาน")],
        default="active",
    )
```

### Form Processing in Views

```python
form = forms.items.ItemForm(request.form)
if request.method == "POST" and form.validate():
    # Process valid form data
    ...
```

---

## 3. Flash Messages & User Feedback

Use Flask's standard `flash()` messaging system with DaisyUI/Tailwind-compatible category names:
- `"success"` — Positive confirmation (e.g. item created, status updated)
- `"error"` or `"danger"` — Validation failure, permission error, DB failure
- `"warning"` — Action completed with caveats or items needing attention
- `"info"` — General informational notice

```python
flash("เพิ่มรายการพัสดุเรียบร้อยแล้ว", "success")
flash("ไม่สามารถลบรายการได้เนื่องจากมีประวัติการเบิกจ่าย", "error")
```

---

## 4. Separation of Concerns (Views vs Controllers vs Repositories)

- **`kampan/web/views/` (Transport Layer)**:
  - Handle HTTP request/response.
  - Form validation via WTForms.
  - ACL and authorization guards.
  - Rendering Jinja2 templates or returning JSON.
- **`kampan/controllers/` (Business Logic Layer)**:
  - Complex state transitions (e.g. procurement workflows, approval steps).
  - Snapshot generation, payment notifications, transaction orchestration.
- **`kampan/repositories/` (Data Access Layer)**:
  - Aggregations, cross-model queries, report compilation, complex query filters.
- **`kampan/utils/` (Cross-cutting Helpers)**:
  - Currency formatting (`format_amount`), date utilities, barcode/QR generators.

---

## 5. Jinja2 Templating Standards

- **Template Inheritance**: Extend base templates (`base/default.html` or similar).
- **Template Filters**: Always use custom filters for formatting:
  ```html
  {{ item.amount | format_amount }} บาท
  {{ item.created_date | format_date }}
  ```
- **Form Error Rendering**: Clearly render field validation errors under each form input.
- **CSRF Token Injection**: Ensure forms include CSRF tokens when CSRF protection is active.

---

## 6. Background Workers (Redis RQ)

Heavy operations (generating PDF reports, batch notifications, bulk exports) must be queued using Redis RQ via `kampan.worker`:

```python
from kampan.web.redis_rq import get_queue

def trigger_report_export(export_id: str):
    queue = get_queue()
    queue.enqueue("kampan.worker.export_worker.generate_export_file", export_id)
```

- Worker tasks must handle their own database connections and exceptions cleanly.
- Persist job status to a tracking model (e.g. `ExportFile`) for frontend polling/feedback.
