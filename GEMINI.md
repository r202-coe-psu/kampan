# Kampan Coding Guidelines & Architecture

Welcome to the Kampan project! To maintain a robust, secure, and clean codebase, follow these development guidelines and architectural rules.

---

## 🏢 1. Multi-Tenancy Architecture
Kampan is a multi-tenant application where data is strictly partitioned by Organization.
* **Model Requirement:** Every tenant-scoped model **MUST** include an `organization` reference field:
  ```python
  organization = me.ReferenceField("Organization", dbref=True, required=True)
  ```
* **Query Scoping:** Always restrict database queries by the current user's organization:
  ```python
  # Correct Scoped Query
  items = models.Item.objects(organization=current_user.organization)
  ```
* **Security:** Never trust input parameters for organization scope. Always fetch and verify it from the authenticated session context (e.g., `current_user`).

---

## 💰 2. Financial & Money Fields
All fields storing currency, prices, budgets, costs, or balances must adhere to strict decimal math to prevent precision loss.
* **Model Requirement:** Always use `me.DecimalField` instead of `me.FloatField` or `me.IntField` for financial figures:
  ```python
  amount = me.DecimalField(required=True, min_value=0, max_value=1e12, precision=2)
  ```
* **Casting & Calculations:**
  * Since Python does not allow direct math operations between `float` and `Decimal`, cast database values to `float` in your view controllers for calculation loops:
    ```python
    item_total += float(allocation.amount or 0)
    ```
  * Assign the final calculations back directly (MongoEngine will automatically serialize them as Decimals on save).
* **Jinja Templating:** Use the `format_amount` filter to display currencies in the templates:
  ```html
  {{ item.amount | format_amount }} บาท
  ```

---

## 🗄️ 3. Database Interaction (MongoEngine ODM)
* **No SQLAlchemy:** Do not use SQLAlchemy. Kampan relies on MongoDB and **MongoEngine**.
* **Assigning Reference Fields:** When saving references to documents (like assigning the creator or modifier), use the underlying raw PyMongo object from `current_user`:
  ```python
  doc.created_by = current_user._get_current_object()
  ```
* **Performance:** Use `.only()` or `.exclude()` when fetching records to optimize performance when querying large collections.

---

## 🌐 4. Route Organization & Forms
* **Blueprints:** Organize routes cleanly into Flask Blueprints. Standard route modules should declare a Blueprint and place successful execution logic at the end of the functions.
* **WTForms:** Always use WTForms for input validation. Define form schemas in `kampan/web/forms/` and perform validation checking in views before processing actions:
  ```python
  form = RequisitionForm(request.form)
  if request.method == "POST" and form.validate():
      # Action logic
  ```

---

## 📁 5. Directory & Naming Conventions
* Filenames, module names, and directory paths must be lowercase, using underscores (`_`) as separators (e.g., `views/procurement/requisition_timeline.py`).
* Class definitions use PascalCase, and variables use snake_case.

---

## 🏗️ 6. Codebase Architecture
The project follows a standard structured model-view-controller/utility layout:
* **`kampan/models/`**: Defines the data models using MongoEngine (documents and embedded documents).
* **`kampan/web/views/`**: Contains Flask route handlers grouped by feature area, organized into Blueprints (e.g., `procurement`, `vehicle_lending`, `admin`).
* **`kampan/web/forms/`**: Holds WTForms definitions matching view/editing requirements.
* **`kampan/web/templates/`**: Holds Jinja2 HTML templates mirroring the views structure.
* **`kampan/controllers/`**: House reusable business logic/services isolated from Flask routing.
* **`kampan/utils/`**: Reusable utility functions and custom template filters (like `format_amount`).
* **`kampan/worker/`**: Background worker tasks (e.g., scheduled operations, heavy jobs).

---

## 🎨 7. Code Styling & Formatting Rules
* **Function Structure**: Use early returns/guard clauses to handle validation or error state at the entry points of your functions. Successful execution flow should be placed at the end.
* **Imports Ordering**: Group imports cleanly:
  1. Standard library imports
  2. Third-party library imports (e.g., `flask`, `mongoengine`)
  3. Local project imports (`kampan.models`, etc.)
* **Typing**: Use type hints (`value: str | float`, `-> Decimal`) in helper functions and service methods to specify parameter and return types clearly.
* **Formatting**: Ensure files end with a single newline, trailing whitespaces are removed, and formatting conforms to PEP 8 standards.

---

## 💅 8. Styling Guidelines (Tailwind CSS & DaisyUI)
All user interfaces in the application must follow clean, responsive styling guidelines:
* **Framework Stack**: The application uses **Tailwind CSS** for custom utilities and layout designs, and **DaisyUI** for clean component classes (e.g., `btn`, `card`, `modal`, `table`).
* **Design Guidelines**:
  * Utilize DaisyUI semantic themes and color classes (`btn-primary`, `text-base-content`, `bg-base-200`) instead of hardcoding raw color hexes or ad-hoc style tags.
  * Ensure the design is fully responsive using Tailwind's layout modifiers (`sm:`, `md:`, `lg:`).

