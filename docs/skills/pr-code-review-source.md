# Agent Skill Source Log: pr-code-review (Kampan)

**Location:** `.agents/skills/pr-code-review/SKILL.md`

ข้อมูลที่นำมาใช้สังเคราะห์เป็น Checklist และแนวทางในไฟล์ `SKILL.md` สำหรับการทำ Code Review ของโปรเจกต์ **Kampan** อ้างอิงจากโครงสร้างมาตรฐานและสถาปัตยกรรมของ Kampan (Python, Flask, MongoEngine, Jinja2, TailwindCSS, DaisyUI) ดังนี้:

### 1. Architecture & Multi-Tenancy (Organization Isolation)
* **แหล่งที่มา**: [GEMINI.md](../../GEMINI.md), [kampan/web/acl.py](../../kampan/web/acl.py), [kampan/models/organizations.py](../../kampan/models/organizations.py)
* **ข้อกำหนดสำคัญ**:
  - Kampan ใช้สถาปัตยกรรมแบบ Multi-Tenancy แยกข้อมูลตาม `Organization` อย่างเคร่งครัด
  - ทุกโมเดลระดับ tenant ต้องมี field `organization = me.ReferenceField("Organization", dbref=True, required=True)`
  - ทุก query ต้องผูกเงื่อนไข `organization=...` เสมอ ห้ามเชื่อถือค่า `organization_id` จาก request payload โดยตรงโดยไม่ผ่านการตรวจสอบสิทธิ์
  - การกำหนดผู้สร้าง/ผู้แก้ไข (`created_by`, `updated_by`) ให้ใช้ `current_user._get_current_object()` เพื่อป้องกันปัญหา proxy object

### 2. MongoDB & MongoEngine ODM Best Practices
* **แหล่งที่มา**: [GEMINI.md](../../GEMINI.md), โค้ดใน [kampan/models/](../../kampan/models/) และ [kampan/repositories/](../../kampan/repositories/)
* **ข้อกำหนดสำคัญ**:
  - ข้อมูลทางการเงิน ตัวเลขงบประมาณ ยอดเงิน ราคา ต้องใช้ `me.DecimalField(precision=2)` เท่านั้น ห้ามใช้ Float หรือ Int
  - ในการคำนวณใน Python ให้แปลงเป็น `float` สำหรับลูปคำนวณ แล้วบันทึกกลับเป็น Decimal โดยตรง
  - ใช้ `.only()` หรือ `.exclude()` เมื่อดึงข้อมูลเพื่อเพิ่มความเร็วในการ query และลด memory footprint
  - หลีกเลี่ยง N+1 query loops เมื่อดึง ReferenceField
  - ใช้ Atomic updates (`update_one`, `modify`, `$inc`, `$push`) สำหรับการเปลี่ยนแปลงสถานะหรือเคาน์เตอร์ที่อาจเกิด race condition

### 3. Flask & Web Standards
* **แหล่งที่มา**: [GEMINI.md](../../GEMINI.md), [kampan/web/views/](../../kampan/web/views/), [kampan/web/forms/](../../kampan/web/forms/)
* **ข้อกำหนดสำคัญ**:
  - แยก route เป็น Flask Blueprints ตามหมวดหมู่ฟังก์ชัน
  - บังคับใช้ WTForms schema ในการตรวจสอบความถูกต้องของข้อมูล (Input validation) และความปลอดภัย CSRF ก่อนประมวลผล
  - ใช้ Early Returns / Guard Clauses ตรวจสอบเงื่อนไขข้อผิดพลาดที่ต้นฟังก์ชัน และวาง Happy path ไว้ท้ายสุด
  - แยก Logic ซับซ้อนไปไว้ใน `kampan/controllers/` หรือ `kampan/repositories/` ไม่ให้วิวหนาเกินไป
  - UI ใช้ Tailwind CSS และ DaisyUI semantic classes ร่วมกับ Custom filter `format_amount`

### 4. PR Review Workflow & Human Review Gate
* **แหล่งที่มา**: มาตรฐาน PR Code Review workflow จาก Tent
* **ข้อกำหนดสำคัญ**:
  - วิเคราะห์และแสดงผลในแชทก่อนเสมอ (Analyze only by default)
  - บันทึกผล review ใน artifact file นอก workspace (`~/.cursor/pr-code-review/`)
  - มีระบบตรวจนับ Review Attempt Threshold (ไม่เกิน 3 ครั้ง) หากเกินจะขึ้น **Escalation notice** ให้ Senior Developer / Tech Lead ตรวจสอบก่อน merge
  - มีการประเมิน **Merge readiness** (พร้อม merge / ยังไม่พร้อม merge / พร้อม merge มีข้อควรระวัง) ชัดเจนทั้งหัวเรื่องและท้ายสรุป
