---
name: mongodb-query-bestpractices
description: Best practices for MongoEngine ODM and MongoDB queries in Kampan. Covers multi-tenancy scoping, DecimalField financial calculations, query optimization (.only/.exclude), ReferenceField handling, indexing, atomic updates, and aggregation pipelines.
---

# MongoDB & MongoEngine Best Practices (Kampan)

Kampan utilizes **MongoDB** via the **MongoEngine ODM** (Object-Document Mapper). Do **not** use SQLAlchemy or raw SQL. All database operations must adhere to multi-tenancy isolation, strict decimal precision, and high-performance query patterns.

---

## 1. Multi-Tenancy Scoping (Crucial)

Every tenant-scoped model **MUST** have an `organization` field:

```python
organization = me.ReferenceField("Organization", dbref=True, required=True)
```

### Mandatory Query Scoping Rule

Every query touching tenant data **MUST** filter by `organization`:

```python
# ✅ CORRECT — Scoped by current user's organization
items = models.Item.objects(
    organization=current_user.organization,
    status="active"
)

# ❌ FORBIDDEN — Unscoped query leaks data across tenants!
items = models.Item.objects(status="active")
```

When querying a single document by ID, always include the organization filter:

```python
# ✅ CORRECT
item = models.Item.objects(id=item_id, organization=organization).first()

# ❌ FORBIDDEN — An attacker could pass another tenant's item_id
item = models.Item.objects(id=item_id).first()
```

---

## 2. Financial & Money Fields (Decimal Math)

Never use `FloatField` or `IntField` for money, prices, budgets, balances, or financial amounts. Always use `DecimalField`.

### Model Definition

```python
amount = me.DecimalField(required=True, min_value=0, max_value=1e12, precision=2)
unit_price = me.DecimalField(required=True, min_value=0, precision=2)
```

### Calculation & Arithmetic Rule

In Python, direct arithmetic between `float` and `Decimal` raises a `TypeError`. Follow this conversion pattern:

```python
# ✅ CORRECT Pattern:
# 1. Cast DB Decimal values to float for calculation loops
total_amount = 0.0
for allocation in item.allocations:
    total_amount += float(allocation.amount or 0)

# 2. Assign the calculated total back (MongoEngine automatically serializes float/Decimal)
item.total_cost = total_amount
item.save()
```

In Jinja templates, format money with the `format_amount` filter:

```html
{{ item.total_cost | format_amount }} บาท
```

---

## 3. ReferenceField Handling & `_get_current_object()`

When assigning the logged-in user to a `ReferenceField` (e.g. `created_by`, `updated_by`, `user`), use `_get_current_object()` to extract the underlying document from Flask-Login's `LocalProxy`:

```python
# ✅ CORRECT
doc.created_by = current_user._get_current_object()
doc.updated_by = current_user._get_current_object()

# ❌ WRONG — Passing LocalProxy can cause serialization or DB reference errors
doc.created_by = current_user
```

---

## 4. Query Optimization (`.only()` / `.exclude()`)

To optimize memory and network throughput when querying large collections, restrict fields fetched from MongoDB:

```python
# Fetch only required fields
items = models.Item.objects(
    organization=organization,
    status="active"
).only("name", "barcode_id", "status", "piece_unit")

# Exclude heavy embedded documents or binary payloads
items = models.Item.objects(organization=organization).exclude("history_logs", "raw_image")
```

---

## 5. Complex Queries with `Q` Expressions

For `OR` conditions or complex filtering, import and use MongoEngine's `Q` object:

```python
from mongoengine import Q

query = Q(organization=organization) & (Q(status="active") | Q(status="pending"))
if search_text:
    query &= (Q(name__icontains=search_text) | Q(barcode_id__icontains=search_text))

items = models.Item.objects(query).order_by("-created_date")
```

---

## 6. Atomic Mutations to Prevent Race Conditions

Avoid read-modify-save cycles for counters or concurrent state updates. Use atomic MongoEngine updates:

```python
# Atomic increment
models.Inventory.objects(id=inventory_id).update_one(
    inc__quantity=-checkout_qty,
    set__updated_date=datetime.datetime.now()
)

# Atomic push to array
models.Requisition.objects(id=req_id).update_one(
    push__timeline_items=timeline_entry
)
```

---

## 7. Aggregation Pipelines for Reports

For reporting and dashboard stats, use MongoDB Aggregation Pipelines via `objects().aggregate(...)`:

```python
pipeline = [
    {"$match": {"organization": organization.id, "status": "active"}},
    {"$group": {"_id": "$category", "total_qty": {"$sum": "$quantity"}, "total_value": {"$sum": "$total_price"}}},
    {"$sort": {"total_value": -1}},
]
results = list(models.Inventory.objects().aggregate(pipeline))
```

---

## 8. Indexing Strategy

Ensure frequently queried and sorted fields are indexed in `meta`:

```python
class Item(me.Document):
    meta = {
        "collection": "items",
        "indexes": [
            "name",
            "status",
            "organization",
            ("organization", "status"),
            ("organization", "-created_date"),
        ],
    }
```
