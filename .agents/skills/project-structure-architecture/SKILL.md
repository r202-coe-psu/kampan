---
name: project-structure-architecture
description: Guidelines for Kampan's codebase architecture, directory structure, multi-agent roles, and coding conventions. Load this when creating new files, features, or deciding where to place logic.
---

# Project Structure & Architecture (Kampan)

Kampan follows a clean Layered Architecture (MVC / Repository / Controller / Worker) tailored for Flask and MongoEngine.

---

## 1. Directory Structure Breakdown

```
kampan/
├── cmd/                  # CLI and server entry points (web.py, worker.py, controller.py)
├── controllers/          # Business logic, state machines, and service orchestrators
├── models/               # MongoEngine Document & EmbeddedDocument definitions
├── repositories/         # Data access aggregations, reports, and complex query repositories
├── utils/                # General helpers, custom Jinja filters, generators
├── worker/               # Background task workers (Redis RQ jobs)
└── web/                  # Web Presentation Layer
    ├── acl.py            # Access Control Lists, RBAC decorators, organization resolution
    ├── forms/            # WTForms form definitions and validators
    ├── redis_rq.py       # Redis Queue integration
    ├── static/           # Static assets (CSS, JS, images, package.json for Tailwind/DaisyUI)
    ├── templates/        # Jinja2 HTML templates mirroring views
    └── views/            # Flask Blueprints and route handlers
```

---

## 2. Layer Responsibilities & Dependency Flow

1. **`web/views/` (Routes)**
   - Depends on: `forms`, `acl`, `controllers`, `repositories`, `models`, `utils`
   - Role: HTTP entrypoint, parameter parsing, form validation, template rendering.
   - Rule: Keep views thin. Route handlers should not contain complex calculation algorithms or direct massive multi-step business transactions.

2. **`controllers/` (Business Logic)**
   - Depends on: `models`, `repositories`, `utils`
   - Role: Reusable business rules, workflow transitions (e.g. `procurement_status.py`, `payment_notifier.py`, `item_snapshot.py`).
   - Rule: Independent of Flask request context where possible so they can be run from CLI, cron, or workers.

3. **`repositories/` (Data Query & Aggregation)**
   - Depends on: `models`
   - Role: Encapsulate heavy MongoDB queries, reporting aggregations, dashboard statistics (e.g. `dashboards.py`, `history_car_lending.py`).

4. **`models/` (Data Schema)**
   - Depends on: `mongoengine`
   - Role: Document schemas, field constraints, metadata and indexes.

5. **`worker/` (Async Jobs)**
   - Depends on: `models`, `controllers`, `repositories`
   - Role: Background batch execution (PDF generation, bulk email, heavy data processing).

---

## 3. Multi-Agent Roles

Kampan organizes agent workflows into 4 specialized roles:

1. **`frontend_agent` (Frontend & Style Specialist)**
   - Audits and updates JavaScript, HTML templates, CSS, Tailwind CSS, and DaisyUI components.
   - Ensures responsive layouts and semantic theme class usage.

2. **`backend_agent` (Backend & Route Specialist)**
   - Manages MongoEngine models, Flask blueprints, WTForms schemas, and controller pipelines.
   - Ensures architecture adherence and clean Python code.

3. **`security_agent` (Security Auditor)**
   - Audits views, models, and forms for multi-tenancy scoping leaks, missing ACL decorators, and CSRF protection.

4. **`test_agent` (Verification Specialist)**
   - Maintains and executes unit/integration tests, verifying multi-tenant isolation, calculations, and regression safety.

---

## 4. Coding & Naming Conventions

- **Filenames & Modules**: `snake_case` (e.g. `requisition_timeline.py`, `item_registers.py`).
- **Classes**: `PascalCase` (e.g. `RequisitionForm`, `DashboardRepository`, `CheckoutItem`).
- **Variables & Functions**: `snake_case` (e.g. `get_item_report()`, `organization_id`).
- **Imports Order**:
  1. Standard library (`datetime`, `decimal`, `functools`)
  2. Third-party packages (`flask`, `mongoengine`, `wtforms`)
  3. Internal Kampan packages (`kampan.models`, `kampan.web.forms`, `kampan.utils`)
