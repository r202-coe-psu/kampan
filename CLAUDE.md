# Kampan: กติกาการทำงานของ Claude

> รวมจาก `GEMINI.md` (กติกาโค้ดของ Kampan) กับ workflow ที่ปรับมาจากโปรเจค `tent` · `GEMINI.md` ตอนนี้ import ไฟล์นี้ (`@CLAUDE.md`) ให้แก้ที่ไฟล์นี้ที่เดียว
> รายละเอียดเชิงลึกอยู่ใน skills ที่ `.claude/skills/` (symlink ไป `.agents/skills/`) ให้โหลด skill ที่ตรงกับงานก่อนลงมือ (ดู §3.7)

---

## 0. กติกาหลัก (อ่านก่อนทุกครั้ง)

1. **ตอบเป็นภาษาไทย** ทุกข้อความที่ผู้ใช้เห็น (code, commit, ชื่อ branch เป็นภาษาอังกฤษได้)
2. **ห้าม merge เอง**: Claude สร้าง PR แล้วรอ ผู้ใช้ทดสอบมือผ่านแล้ว**ผู้ใช้ merge เข้า `develop` เอง**
3. **ไม่แจ้งหรือขอ review จากใคร**: ไม่ใส่ reviewer ไม่ @mention ไม่คอมเมนต์เรียกใคร
4. **ห้าม `--no-verify`** และห้ามข้าม hook ทุกกรณี ถ้า hook ล้มให้แก้ที่ต้นเหตุ (ตอนนี้ repo ยังไม่มี hook ดู §2.4)
5. **ไม่ใส่ attribution ของ Claude** (`Co-Authored-By: Claude`, `Generated with Claude Code`) ใน commit, PR หรือ issue
6. **ห้ามแก้ spec หรือ requirement เงียบ ๆ**: ถ้าต้องเปลี่ยนกติกา, schema หรือสิทธิ์ ให้หยุดถามผู้ใช้ก่อนว่าจะบันทึกแบบไหน (ดู §7)
7. **งานที่ย้อนยากหรือออกไปข้างนอก** (push, เปิด PR/issue, ลบข้อมูล, kill process, แก้ข้อมูลใน DB ที่ไม่ใช่ข้อมูลทดสอบที่สร้างเอง) ทำได้เมื่อผู้ใช้สั่ง หรือเป็นส่วนของงานที่ตกลงกันแล้วเท่านั้น
8. **ถามก่อนเริ่มงานนอกขอบเขตที่ตกลง**: เจองานใหม่ระหว่างทางให้เสนอเปิด issue แยก ไม่ทำเอง

---

## 1. โปรเจค Kampan

ระบบบริหารพัสดุแบบ multi-tenant (แยกข้อมูลตาม Organization) มี 3 ระบบหลัก:
- **คลังวัสดุ / เบิกวัสดุ**: items, inventories, item_orders, item_checkouts, approve_orders, lost_breaks ฯลฯ
- **ขอซื้อขอจ้าง / MA**: `views/procurement/` (requisition, requisition_timeline, products, payment) และ MAS
- **ยานพาหนะ**: `views/vehicle_lending/` (รถยนต์, มอเตอร์ไซค์, สิทธิ์อนุมัติ, งานคนขับ, แบบประเมิน)

**Stack:** Flask 3 + MongoEngine (MongoDB) + Redis RQ + Jinja2 + Tailwind v4 / DaisyUI (ธีม `patsara`) + jQuery / htmx · Python ≥ 3.11 · Poetry

### 1.1 Process ที่รัน (ดู `pyproject.toml` และ `docker-compose.*.yml`)
| process | entry | หน้าที่ |
|---|---|---|
| web | `kampan-web` → `kampan.web:create_app()` | Flask app (prod: gunicorn port 10060, dev: default port 8081) |
| worker | `kampan-worker` → `kampan/worker/server.py` | RQ worker queue `default`: ส่งอีเมล, export/import ไฟล์ |
| controller | `kampan-controller` → `kampan/controllers/server.py` | asyncio loop งานตามเวลา: snapshot ของคงคลังทุกวันที่ 1 (00:05), อัปเดตสถานะ procurement (00:01), แจ้งเตือนชำระ MA (00:10) |

- งานที่ enqueue เข้า RQ จะรันใน **worker** ถ้าแก้โค้ดใน `kampan/utils/*email*`, `export_file.py`, `upload_files.py` ต้อง restart worker ให้โค้ดใหม่มีผล
- **Config:** web อ่านจาก env → ไฟล์ `KAMPAN_CFG` → `KAMPAN_SETTINGS` (บรรทัดที่โหลด `default_settings.py` ใน web ถูก comment ไว้) ส่วน worker/controller ใช้ `kampan/utils/config.py` ซึ่งโหลด `default_settings.py` ก่อน
- ไฟล์ `*.cfg` ถูก gitignore จึงไม่ถูก copy ไปใน worktree ให้ชี้ไปที่ `kampan-development.cfg` ของ repo หลัก

### 1.2 คำสั่งที่ใช้บ่อย (รันจาก root ของ repo/worktree)
`venv/` มีแค่ใน repo หลัก ถ้าอยู่ใน worktree ให้ใช้ `<repo หลัก>/venv/bin/...` แทน
```bash
venv/bin/python -m pytest -q                         # เทสต์ทั้งหมด (~3 วินาที, mongomock ไม่ต้องมี DB)
venv/bin/python -m pytest tests/test_x.py -k name    # เทสต์เฉพาะ
PYTHONPATH=$(pwd) venv/bin/python scripts/check_module_boundaries.py  # ขอบเขต module + url_for ที่อ้าง endpoint ไม่มีจริง
venv/bin/black <ไฟล์ที่แตะ>                            # format (scripts/format.sh = black kampan)
venv/bin/flake8 <ไฟล์ที่แตะ>
./scripts/npm run tw:watch                           # build CSS (Tailwind) ระหว่างพัฒนา
./scripts/run-web | run-worker | run-controller      # dev server ของ repo หลัก
venv/bin/python scripts/seed_mock_users.py [--clear] # สร้าง/ลบ user ปลอม (@mock.kampan.local) สำหรับทดสอบมือ
```

### 1.3 CI / branch
- PR ชี้เข้า `develop`
- `develop` → Jenkins (`Jenkinsfile`, poll ทุก 5 นาที) build `Dockerfile.staging` แล้ว deploy staging ผ่าน `scripts/deploy-staging.sh` (`docker-compose.staging.yml`)
- `main` → production (Jenkins ผ่าน ssh และ `.github/workflows/cicd.yml`)
- CI **ไม่รันเทสต์** ทำแค่ build + deploy เทสต์จึงต้องรันในเครื่องก่อน push เสมอ

---

## 2. วงจรงาน 1 issue (ทำตามลำดับ)

```
issue → อ่าน/วิเคราะห์ → (ถ้ากระทบ spec: ถามผู้ใช้ + ร่าง CR) → worktree/branch → ลงมือ
     → เทสต์ + lint → self review (agent อิสระ) → แก้ → commit/push → draft PR
     → ส่งขั้นตอนทดสอบมือ → ผู้ใช้ทดสอบ → (ไม่ผ่าน: แก้วนกลับ) → ผ่าน: PR ready + อัปเดต issue
     → ผู้ใช้ merge เอง
```

### 2.1 อ่านและวิเคราะห์ก่อนลงมือ
- อ่าน issue ทั้งหมด รวมคอมเมนต์ และเอกสาร spec ที่เกี่ยวข้อง (`docs/specs/`, `docs/testing.md`)
- **ตรวจโค้ดจริงก่อนตอบ** ห้ามเดาจากชื่อไฟล์ ถ้าผู้ใช้ถามว่า "ทำไปแล้วยัง / อยู่ PR ไหน / ระบบทำงานยังไง" ให้ค้นโค้ด, git และ gh ก่อนตอบ
- เทียบ issue กับ spec และงานที่ merge แล้ว ถ้าขัดกันให้**หยุดถามผู้ใช้** พร้อมทางเลือก 2–3 ทางและข้อแนะนำ
- คำถามที่ผู้ใช้ต้องตัดสิน: ให้เป็นตัวเลือก A / B / C สั้น ๆ บอกว่าแนะนำข้อไหนเพราะอะไร ให้ผู้ใช้ตอบสั้น ๆ ได้ เช่น "1A 2B"

### 2.2 worktree / branch
- 1 issue = 1 branch = 1 worktree แตกจาก `origin/develop` ล่าสุดเสมอ (`git fetch` ก่อน) ห้ามทำงานบน `main` หรือ `develop` ตรง ๆ
- ชื่อ branch: `<type>-<short-desc>` ภาษาอังกฤษตัวเล็ก เช่น `fix-requisition-approver-role`
  ```bash
  git fetch origin
  git worktree add ../kampan-<branch> -b <branch> origin/develop
  ```
- **ข้อควรระวังใน worktree:**
  - `venv` ของ repo หลักติดตั้ง kampan แบบ editable ชี้ไปที่ repo หลัก (`kampan.pth`) ถ้ารัน `kampan-web` จาก worktree ตรง ๆ จะได้**โค้ดของ repo หลัก** ต้องใส่ `PYTHONPATH=$(pwd)` เสมอ (pytest ไม่มีปัญหาเพราะ `pytest.ini` ตั้ง `pythonpath = .`)
  - `app.css` และ `node_modules` ถูก gitignore ต้อง build CSS ใน worktree เอง: `./scripts/npm install && ./scripts/npm run tw`
  - ใช้ npm ตาม Dockerfile (`package-lock.json`) ไม่ใช้ pnpm

### 2.3 ลงมือ
- งานเล็กหรือแตะไฟล์น้อย: ทำเอง
- งานใหญ่: แบ่งให้ **sub-agent** ทำใน worktree ของงานนั้น แยกตามชั้นงานได้ (frontend / backend / security / test ดู §3.7) brief ให้ครบ: เป้าหมาย, ไฟล์ที่ต้องอ่าน, skill ที่ต้องโหลด, spec ที่ผูกพัน, ข้อห้าม (ห้าม commit, push หรือแตะ GitHub), เทสต์ที่ต้องมี, คำสั่งตรวจ, รูปแบบรายงานกลับ
- เขียนโค้ดให้กลืนกับโค้ดรอบข้าง (ชื่อ, สไตล์, ความหนาแน่นของ comment) และทำตามกติกาใน §3
- ข้อมูลหรือ logic ใหม่ต้องมีเทสต์ ถ้าแก้บั๊กต้องมีเทสต์ที่**ล้มถ้าเอา fix ออก** (ลองถอด fix แล้วรันให้เห็นว่าล้มจริง)

### 2.4 ตรวจก่อน commit
- repo นี้**ยังไม่มี pre-commit / pre-push hook** และ CI ก็ไม่รันเทสต์ Claude จึงต้องรันเอง:
  1. ระหว่างพัฒนา รันเฉพาะเทสต์ที่แตะ
  2. **ก่อน commit/push ทุกครั้ง** รัน `venv/bin/python -m pytest -q` ทั้ง suite (เร็วมาก) และ `scripts/check_module_boundaries.py` ถ้าแตะ views หรือ templates
- เป้าหมายคือ zero regression ถ้ามีเทสต์ที่ล้มอยู่แล้วบน `origin/develop` ให้ยืนยันด้วยการรันบน develop แล้วแจ้งผู้ใช้แยกว่า "ล้มอยู่ก่อน ไม่ใช่ของ PR นี้" ห้ามแก้เทสต์ให้ผ่านเฉย ๆ
- `black` และ `flake8` เฉพาะไฟล์ที่แตะ (ไม่ format ทั้งโปรเจค เพราะจะทำให้ diff บวม)
- งาน UI / template: เปิด dev server ของ worktree แล้วดูของจริงหรือ screenshot ถ้าทำได้

### 2.5 self review ด้วย agent อิสระ (ทำคู่กับการแก้)
- เมื่อโค้ดพร้อม หรือมี review ให้แก้: เปิด **2 agent ขนานกัน**
  1. **agent แก้**: แก้ตามรายการใน worktree
  2. **agent รีวิวอิสระ (model ที่เก่งกว่า)**: อ่านเฉพาะ branch ที่ push แล้วผ่าน git objects (`git diff origin/develop...origin/<branch>`) ห้ามแก้ไฟล์ และใช้ checklist ของ skill `pr-code-review` บอกให้**ไม่ต้องรายงานซ้ำ**เรื่องที่รู้อยู่แล้ว ให้หาเฉพาะบั๊ก, ผิด spec, race, สิทธิ์ / multi-tenant leak, ข้อมูลหลุด และเทสต์ที่ผ่านทั้งที่มีบั๊ก ทุกข้อต้องยืนยันด้วยการอ่านโค้ดจริง
- Claude ตรวจผลของทั้งสอง agent เองก่อนเชื่อ:
  - ข้อที่ยืนยันได้ → ส่งให้ agent แก้เพิ่ม
  - ข้อที่เป็นการตัดสินใจเชิง spec → ถามผู้ใช้
  - ข้อที่เสี่ยงต่ำหรือมีอยู่ก่อน PR → บอกผู้ใช้ว่าไม่แก้เพราะอะไร
- **อ่าน diff ของ agent เองทุกครั้งก่อน commit** โดยเฉพาะส่วนที่เกี่ยวกับสิทธิ์, การ scope ตาม organization, ข้อมูลส่วนตัว และการเขียน DB

### 2.6 commit / push
- Conventional Commits: `<type>(<scope>): <imperative summary>` ยาวไม่เกิน 72 ตัวอักษร ตัวพิมพ์เล็กหลัง `:` และ body อธิบาย "ทำไม" สั้น ๆ
  - scope ที่ใช้อยู่: `vehicle-lending`, `car-manuals`, `procurement`, `requisition`, `inventory`, `email`, `server`, `docker` ฯลฯ
- ถ้าเทสต์ล้ม: อ่าน output หาเทสต์ที่ล้ม แล้วแยกให้ได้ว่าเป็นของ PR นี้, ของ develop เอง (เช่น 2 PR ที่ merge แล้วชนกัน) หรือ environment แล้วแก้ที่ต้นเหตุ ถ้า develop พังเพราะงานของ Claude เอง ให้เปิด PR แก้แยกทันทีและบอกผู้ใช้

### 2.7 PR
- เปิดเป็น **draft PR ทันทีหลัง push** ชี้เข้า `develop` **ไม่ใส่ reviewer ไม่แจ้งใคร ไม่ใส่ attribution**
- body (ภาษาไทย):
  ```
  ## สรุป
  <1-3 บรรทัด: ทำอะไร เพื่ออะไร>
  - <bullet ของสิ่งที่เปลี่ยน แยกตามเรื่อง>
  **ไม่อยู่ใน PR นี้:** <ถ้ามี>
  **deploy:** <restart worker/controller / สร้าง index / migration script — ถ้ามี>

  ## การตรวจสอบ
  - unit / integration: <ไฟล์ + กรณีที่ครอบ>
  - pytest ทั้ง suite: <ผ่าน x / ล้ม y (ระบุถ้าล้มอยู่ก่อนบน develop)>
  - black / flake8: <ผล>
  - ทดสอบมือ: รอ

  Closes #<issue>   (หรือ Refs #<issue> ถ้า PR นี้ทำแค่บางส่วนของ issue)
  ```
- PR ที่แก้เพิ่มหลังผู้ใช้ทดสอบ: push ต่อ branch เดิม แล้วอัปเดต body ให้ตรง

### 2.8 ขั้นตอนทดสอบมือ (ส่งให้ผู้ใช้ทุกครั้งหลังเปิด PR)
- **รูปแบบบังคับ:** ข้อเลข + `ทำอะไร:` / `ผลที่ต้องได้:` (ไม่ใช้ตาราง เพราะผู้ใช้แนบรูปใต้แต่ละข้อ)
  ```
  1. <ชื่อข้อ>
     ทำอะไร: <ไปหน้าไหน (URL เต็ม รวม ?organization_id=...) / กดอะไร / ใช้ข้อมูลอะไร / login เป็นใคร (role ไหน)>
     ผลที่ต้องได้: <สิ่งที่ต้องเห็น / ค่าที่ต้องเปลี่ยนใน DB>
  ```
- ถ้างานแตะสิทธิ์หรือข้อมูลข้าม org ให้มีข้อทดสอบ "ผู้ใช้ org อื่น / role ที่ไม่มีสิทธิ์ เข้าไม่ได้" ด้วยเสมอ
- **เตรียมให้พร้อมกด:**
  - เปิด dev server ของ worktree บน port แยก (บอก port ให้ผู้ใช้):
    ```bash
    PYTHONPATH=$(pwd) KAMPAN_SETTINGS=<repo หลัก>/kampan-development.cfg \
      <repo หลัก>/venv/bin/kampan-web -H 0.0.0.0 -P <port> -d
    ```
  - สร้างข้อมูลทดสอบให้ (ผ่านหน้าเว็บหรือ route จริงถ้าทำได้ หรือเขียน DB ตรงเฉพาะข้อมูลทดสอบ) แล้วให้**ลิงก์ที่กดได้เลย**
  - บอกวิธีดูค่าใน DB ถ้าต้องตรวจ: dev ใช้ MongoDB ที่ `localhost:27017` db `kampandb` (เครื่องนี้ไม่มี `mongosh` ให้ใช้ `docker exec -it <mongo container> mongosh kampandb`) และ Redis ใช้ `redis-cli`
- ตั้งชื่อข้อมูลทดสอบให้รู้ว่าเป็นของทดสอบ (ขึ้นต้น `[TEST]`) และ**ลบให้หลังผู้ใช้บอกว่าเสร็จ** ถ้าต้องการ user จำนวนมากให้ใช้ `scripts/seed_mock_users.py` (ลบด้วย `--clear`)
- ถ้าผู้ใช้บอกว่า "ข้อ X ไม่ผ่าน": ตรวจข้อมูลจริง (DB / log) ก่อนสรุป แยกให้ได้ว่าเป็นบั๊กของ PR, ข้อมูลทดสอบไม่ตรงเงื่อนไข หรือ environment (เช่น worker ยังรันโค้ดเก่า, CSS ยังไม่ build) แล้วอธิบายสั้น ๆ

### 2.9 หลังผู้ใช้ทดสอบผ่าน
- `gh pr ready <n>` แล้วอัปเดต body ส่วน "ทดสอบมือ — ผ่าน: <สรุปสิ่งที่ทดสอบ>"
- ติ๊ก acceptance criteria ใน issue เฉพาะข้อที่ทดสอบผ่านจริง
- board: GitHub Project **"kampan"** (#15, owner `r202-coe-psu`) มีสถานะ `Backlog / Todo / In Progress / Done`
  - เริ่มทำ → `In Progress`
  - merge แล้ว → `Done` (ทำตอน "ตรวจ PR" §6)
- label ที่ใช้: `bug`, `enhancement`, `documentation`, `needs-info`, `ready-for-agent`
- **ไม่แจ้งใคร** ผู้ใช้ merge เข้า `develop` เอง

---

## 3. กติกาเขียนโค้ด Kampan

### 3.1 Multi-tenancy (สำคัญที่สุด)
- model ที่เป็นข้อมูลของหน่วยงาน**ต้องมี** `organization = me.ReferenceField("Organization", dbref=True, required=True)`
- **ทุก query ต้อง scope ด้วย organization** รวมถึงการดึงด้วย id:
  ```python
  item = models.Item.objects(id=item_id, organization=g.organization).first()
  if not item:
      abort(404)
  ```
  ห้ามใช้ `Model.objects.get(id=...)` หรือ `.objects(id=...)` โดยไม่กรอง org
- **ห้ามเชื่อ organization จาก input**: ใช้ `g.organization` ที่ `acl.resolve_viewing_organization` ตั้งให้ (ซึ่งตรวจ membership แล้ว) ห้ามดึง org จาก `request.form["organization_id"]` มาใช้เอง และห้ามเปลี่ยน `obj.organization` ตอนแก้ไขข้อมูล
- ตรวจสิทธิ์ฝั่ง server เสมอด้วย `@acl.organization_roles_required(...)` การซ่อนปุ่มที่ UI ไม่ใช่การป้องกัน ถ้า role มาจาก input (เช่น `approver_role`) ต้องเทียบกับ role จริงของ `current_user` ใน org นั้น
- role ระดับระบบอยู่ที่ `User.roles` ส่วน role ใน org อยู่ที่ `OrganizationUserRole.roles` และ global admin ผ่าน `organization_roles_required` ได้ทุก org
- พฤติกรรมของ ACL ที่ต้องรู้ตอนเขียนเทสต์: `acl.py` ดัก 403 แล้ว **redirect (302) ไปหน้า login**

### 3.2 การเงิน
- ใช้ `me.DecimalField(precision=2, ...)` กับเงินทุกชนิด ห้ามใช้ Float/Int
- คำนวณด้วย `Decimal` (สร้างจาก `str` ไม่ใช่ `float` เพื่อเลี่ยง binary noise) และห้ามตัดทศนิยมด้วย `int()`
- template แสดงเงินด้วย `{{ value | format_amount }} บาท`

### 3.3 MongoEngine
- ไม่ใช้ SQLAlchemy
- ReferenceField ของผู้ใช้: `doc.created_by = current_user._get_current_object()`
- ใช้ `.only()` / `.exclude()` กับ collection ใหญ่ และระวัง N+1 query ใน loop
- การตัด stock หรือลดยอด (เช่น `reservable_amount`) ต้องตรวจยอดคงเหลือ และใช้ atomic update (`update_one(dec__...)` พร้อมเงื่อนไข) ถ้ามีโอกาสกดพร้อมกัน
- เปลี่ยน shape ของ document ต้องอ่านของเก่าได้ ถ้าต้อง migrate ให้เขียน script ใน `scripts/` (ดูตัวอย่าง `backfill_car_feedback_organization.py`)

### 3.4 Route, Form และ Email
- route จัดเป็น Blueprint (`module = Blueprint(...)` ใน `kampan/web/views/`) ระบบโหลด blueprint อัตโนมัติจาก `views/__init__.py`
- โครงฟังก์ชัน: ใช้ guard clause / early return ช่วงต้น แล้ววาง flow ที่สำเร็จไว้ท้ายฟังก์ชัน
- input ต้องผ่าน WTForms (`kampan/web/forms/`) และเช็ค `form.validate_on_submit()` ก่อนทำงาน ห้ามอ่าน `request.form` ดิบมาเขียน DB
- การเปลี่ยนสถานะหรือลบข้อมูลต้องเป็น **POST** ไม่ใช่ GET
- งานหนักและอีเมลให้ enqueue ผ่าน `redis_rq.redis_queue.queue.enqueue(...)` แล้วไปรันใน worker
- views ควรบาง ย้าย logic ที่ใช้ซ้ำไป `controllers/` หรือ `utils/` และ query/aggregation หนัก ๆ ไป `repositories/`

### 3.5 Naming และสไตล์
- ไฟล์, module และ directory ใช้ `snake_case` ตัวเล็ก · class ใช้ `PascalCase` · ตัวแปรและฟังก์ชันใช้ `snake_case`
- ลำดับ import: stdlib → third-party (`flask`, `mongoengine`) → local (`kampan...`)
- ใส่ type hints ใน helper และ service ใหม่
- PEP 8 (black) ไฟล์จบด้วย newline 1 บรรทัด และไม่มี trailing whitespace

### 3.6 UI (Tailwind + DaisyUI)
- template อยู่ที่ `kampan/web/templates/` จัดโครงให้ตรงกับ views และสืบทอดจาก `base/base.html` ผ่าน base ของแต่ละระบบ (`base/template-page-login.html`, `vehicle_lending/base/`, `procurement/base/`)
- ใช้ class ของ DaisyUI ที่อิงธีม (`btn-primary`, `bg-base-200`, `text-base-content`, `text-error`) แทน hex หรือสีดิบ
- รองรับ responsive ด้วย `sm:` / `md:` / `lg:`
- ไม่ใช้ `alert()` หรือ `confirm()`: ใช้ inline field error (`vehicle_lending/components/field_error.html`) และ modal ยืนยันแทน
- แก้ template แล้วต้อง build CSS ใหม่ (`./scripts/npm run tw` หรือ `tw:watch`)

### 3.7 Skills ที่ต้องโหลดตามงาน
| งาน | skill |
|---|---|
| วางไฟล์ใหม่หรือเลือกชั้นที่จะใส่ logic | `project-structure-architecture` |
| route, form, worker | `flask-bestpractices` |
| model และ query | `mongodb-query-bestpractices` |
| สิทธิ์และ multi-tenant | `security-rbac-bestpractices` |
| template และ UI | `daisyui-tailwind-bestpractices` |
| เทสต์ | `testing-bestpractices` (+ `docs/testing.md`) |
| รีวิว | `pr-code-review` |

### 3.8 เทสต์
- pytest + `mongomock` (`tests/conftest.py`) ไม่ต้องมี DB จริง ระบบล้าง collection ทุกเทสต์ให้อัตโนมัติ
- fixtures ที่มีให้: `app`, `create_org`, `create_user`, `assign_user_to_org`, `login_as`, `create_car`, `create_car_application`, `create_feedback_template` / `response`, `make_question`, `make_answer`
- ทุก route ที่แตะข้อมูลของ org ควรมีเทสต์ cross-tenant (ผู้ใช้ org A เข้าถึงข้อมูล org B ไม่ได้) และเทสต์ role ที่ไม่มีสิทธิ์
- endpoint สาธารณะ (เช่นแบบประเมิน QR `cars.py`) ต้องมีเทสต์ยืนยันว่าไม่มี PII หลุด

---

## 4. หลักการคิด

- **ข้อเท็จจริงก่อนความเห็น:** ทุกคำตอบเรื่องสถานะ, โค้ด หรือข้อมูล ต้องมาจากการตรวจจริง (git, gh, DB, test output) ถ้ายังไม่ได้ตรวจให้บอกว่ายังไม่ได้ตรวจ
- **ไม่อ้างว่าเสร็จถ้ายังไม่เสร็จ:** แยกให้ชัดว่าอยู่ขั้นไหน "commit ในเครื่อง / push แล้ว / PR เปิดแล้ว / เทสต์ผ่าน / ผู้ใช้ทดสอบผ่าน / merge แล้ว" ถ้าเทสต์ล้มให้บอกพร้อม output
- **เล็กและแยกได้:** 1 issue 1 PR งานที่พบระหว่างทางเปิด issue ใหม่ ไม่ยัดรวม
- **ไม่ขยาย scope เอง:** ทำตามที่ตกลง ถ้าเห็นสิ่งที่ควรทำเพิ่มให้เสนอเป็นตัวเลือก
- **กันข้อมูลเก่า:** เปลี่ยน shape ของ document ต้องอ่านของเก่าได้ และต้องหยุดแหล่งที่ยังเขียนรูปแบบเก่า (ต้นทาง) ด้วย
- **ความเป็นส่วนตัวและสิทธิ์:** endpoint สาธารณะคืนเฉพาะ field ที่จำเป็น scope ทุก query ด้วย org (§3.1) และตรวจสิทธิ์ฝั่ง server
- **ความล้มเหลวบางส่วน:** ข้อมูลเสริมที่ดึงไม่ได้ (รวมถึงส่งอีเมลไม่สำเร็จ) ต้องไม่ทำให้ทั้งหน้าล่ม ให้ fallback เป็นค่าว่างพร้อม log แต่**ห้ามกลืน error เงียบ ๆ** แล้วรายงานว่าสำเร็จ
- **concurrency:** คิดเสมอว่าถ้า 2 คนกดอนุมัติพร้อมกัน, หน้าจอค้างข้อมูลเก่า หรือ retry หลัง timeout จะเขียนซ้ำหรือทับกันไหม (เช่น ตัด stock หรือ reservation ซ้ำ)
- **แนะนำ 1 ทาง:** เวลามีทางเลือก ให้บอกว่าแนะนำข้อไหนและเพราะอะไร ไม่ไล่ทุกทางแบบเท่ากัน

---

## 5. การสื่อสารกับผู้ใช้

- สั้น ตรง ภาษาไทย บรรทัดแรกคือคำตอบหรือผลลัพธ์ แล้วค่อยตามด้วยรายละเอียด
- ใช้ตารางเมื่อเทียบหลายรายการ (สถานะ PR, ตัวเลือก) และใช้ข้อเลขเมื่อเป็นลำดับขั้น
- ทุก URL และ path ให้ครบพร้อมกด อ้างโค้ดเป็น `path:line`
- จบด้วย "สิ่งที่รอคุณ" เมื่อมีเรื่องต้องตัดสินใจ
- ถ้าผู้ใช้ถามว่า "ต้องทำอะไรต่อ": ตรวจสถานะจริงทุก PR และ issue ก่อน แล้วสรุปเป็น 3 กลุ่มเรียงตามความสำคัญ: ฝั่ง Claude กำลังทำ · สิ่งที่ผู้ใช้ต้องทำหรือตัดสิน · รอ (ไม่ต้องทำอะไร)
- รายงานงานที่ agent ทำ: สรุปเป็นภาษาของผู้ใช้ ไม่ copy รายงานของ agent มาทั้งก้อน

---

## 6. ตรวจ PR ที่เปิดอยู่ (เมื่อผู้ใช้สั่ง "ตรวจ PR")

1. `gh pr list --author @me --state open` และดูสถานะ draft / mergeable ของแต่ละตัว
2. หา conflict กับ `develop` (`git merge-tree --write-tree origin/develop origin/<branch>`) ถ้ามี ให้แก้ใน worktree ของ PR นั้น (merge develop เข้า branch แล้ว push)
3. คอมเมนต์หรือ review ใหม่จากใครก็ตาม → สรุปเป็นรายการให้ผู้ใช้ แยกเป็น "แก้ได้เลย" กับ "ต้องตัดสินใจ"
4. PR ที่ merge แล้ว → ปิด issue, ย้าย board เป็น `Done`, ลบ worktree ที่ไม่ใช้ (`git worktree remove`)
5. ตอบเป็นตาราง: PR | สถานะ | ต้องทำอะไร

---

## 7. Spec / Change Record

- spec ที่มีตอนนี้อยู่ใน `docs/specs/` (หน้าคู่มือของ procurement และระบบเบิกวัสดุ) และ `docs/testing.md`
- การเปลี่ยนที่ต้องบันทึก: field ของ document, กติกา / enum / invariant (เช่นลำดับสถานะการอนุมัติ), สิทธิ์ / role, scope / ลำดับงาน
- **ก่อนแก้ ถามผู้ใช้ทุกครั้งว่าจะบันทึกแบบไหน** (แก้ไฟล์ spec + Amendment / ร่าง CR ใหม่ / วิธีอื่น) ไม่มีค่า default
- ร่าง CR เขียนถึง developer ตามลำดับ: สรุป (TL;DR) ไม่เกิน 4 บรรทัด → Why → FR เป็นข้อ ๆ ที่ทดสอบได้ → ตาราง before → after → Acceptance → Impact → Migration → Decision log (วันที่ + ใครตัดสิน)
- ห้ามรันเลข CR เอง ห้ามตั้งสถานะ `approved` เอง ให้ร่างเป็นไฟล์ MD ให้ผู้ใช้อ่านก่อน แล้วค่อยเปิด PR เมื่อผู้ใช้โอเค
- เมื่อแก้ spec: แก้ docs ก่อนแล้วโค้ดตาม และอัปเดต `updated:` ของเอกสารเป็นวันที่จริง

---

## 8. ข้อมูลทดสอบและ environment

- สร้างข้อมูลทดสอบผ่านหน้าเว็บหรือ route จริงก่อน (จะได้ผลเหมือนผู้ใช้จริง เช่น `requisition_code`, ordinal number, approval history) แล้วค่อยแก้ DB ตรงเพื่อจำลองสถานะพิเศษ
- ก่อนลบ: ตรวจว่าเป็นข้อมูลที่ Claude สร้างเอง (ชื่อ `[TEST]` + เวลาสร้าง + ผู้สร้าง) และลบที่เกี่ยวข้องให้ครบ (เช่น Requisition → RequisitionTimeline, Reservation)
- งานที่รันใน worker หรือ controller (อีเมล, export, งานตามเวลา): ถ้าทดสอบโค้ดจาก branch ต้องรัน worker จาก worktree นั้นด้วย `PYTHONPATH=$(pwd)` และบอกผู้ใช้ว่าตอนนี้ worker รันโค้ดของ branch ไหน
- ถ้าใช้ docker compose: `docker compose -p <project> --env-file <repo หลัก>/kampan-development.cfg -f docker-compose.development.yml up -d --build --no-deps <service>` เพื่อไม่สร้าง stack ใหม่ที่ชื่อชนกัน
- เครื่องนี้มี container ของโปรเจคอื่น (เช่น `tent-*`) รันอยู่ด้วย ห้ามแตะ ถ้าเครื่องทำงานหนักให้บอกผู้ใช้ว่ามี dev server หรือ process ไหนปิดได้ (ให้คำสั่ง `! kill ...` ให้ผู้ใช้รันเอง)

---

## 9. Memory ที่ควรบันทึก (ถ้าใช้ระบบ memory)

- คำตัดสินของผู้ใช้ที่ใช้ซ้ำได้ (พร้อมเหตุผล)
- ไม่บันทึกสิ่งที่อยู่ในไฟล์นี้แล้ว หรือดูได้จาก git / code อยู่แล้ว
