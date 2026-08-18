---
name: daisyui-tailwind-bestpractices
description: Best practices for frontend UI, Tailwind CSS, DaisyUI components, and Jinja2 template styling in Kampan. Load this when creating or updating templates and UI components.
---

# Tailwind CSS & DaisyUI Best Practices (Kampan)

Kampan uses **Tailwind CSS** combined with **DaisyUI** component classes for building clean, responsive, themeable web interfaces in Jinja2 templates.

---

## 1. Core Principles

1. **Semantic DaisyUI Classes First**: Use DaisyUI components (`btn`, `card`, `table`, `modal`, `badge`, `alert`, `tabs`) rather than creating ad-hoc custom styles with raw utility chains.
2. **Semantic Theme Colors**: Use theme-aware color classes (`btn-primary`, `text-base-content`, `bg-base-100`, `bg-base-200`, `badge-success`) instead of hardcoded colors like `bg-[#1a2b3c]` or `text-blue-500`.
3. **Mobile-First Responsive Layouts**: Utilize Tailwind's breakpoint prefixes (`sm:`, `md:`, `lg:`, `xl:`) for grid and flex layouts.

---

## 2. Common Component Patterns

### Buttons

```html
<!-- Primary action -->
<button type="submit" class="btn btn-primary">บันทึกข้อมูล</button>

<!-- Secondary action / cancel -->
<a href="{{ url_for('items.index') }}" class="btn btn-ghost">ยกเลิก</a>

<!-- Danger action -->
<button class="btn btn-error btn-outline btn-sm">ลบรายการ</button>
```

### Tables

```html
<div class="overflow-x-auto bg-base-100 rounded-box shadow">
  <table class="table table-zebra w-full">
    <thead>
      <tr>
        <th>#</th>
        <th>ชื่อวัสดุ</th>
        <th>จำนวน</th>
        <th>ราคาต่อหน่วย</th>
        <th>จัดการ</th>
      </tr>
    </thead>
    <tbody>
      {% for item in items %}
      <tr class="hover">
        <td>{{ loop.index }}</td>
        <td class="font-medium">{{ item.name }}</td>
        <td>{{ item.quantity }} {{ item.piece_unit }}</td>
        <td>{{ item.price | format_amount }} บาท</td>
        <td>
          <a href="{{ url_for('items.edit', item_id=item.id) }}" class="btn btn-sm btn-ghost">แก้ไข</a>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
```

### Cards & Panels

```html
<div class="card bg-base-100 shadow-md">
  <div class="card-body">
    <h2 class="card-title text-lg font-bold">ข้อมูลพัสดุ</h2>
    <!-- Form or content -->
  </div>
</div>
```

### Alerts & Flash Messages

```html
{% with messages = get_flashed_messages(with_categories=true) %}
  {% if messages %}
    <div class="space-y-2 mb-4">
      {% for category, message in messages %}
        <div role="alert" class="alert {% if category == 'success' %}alert-success{% elif category in ['error', 'danger'] %}alert-error{% elif category == 'warning' %}alert-warning{% else %}alert-info{% endif %}">
          <span>{{ message }}</span>
        </div>
      {% endfor %}
    </div>
  {% endif %}
{% endwith %}
```

---

## 3. Formatting Filters in Templates

Always use predefined Jinja filters:
- Currency / Money: `{{ value | format_amount }}`
- Date: `{{ value.strftime('%d/%m/%Y %H:%M') }}`
