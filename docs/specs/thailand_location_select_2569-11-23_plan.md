# แผน: เลือก จังหวัด / อำเภอ / ตำบล แบบ dropdown ต่อกัน (ใช้ข้อมูลจาก tent)

วันที่: 2569-11-23

## ตอนนี้เป็นอย่างไร

- ช่อง ต./อ./จ. ในใบขอใช้รถทั้งหมดเป็น `StringField` ที่ให้ผู้ใช้พิมพ์เอง ไม่มีการตรวจสอบค่า
  - `domestic`: `district`, `province` ([models/car_reservations.py](../../kampan/models/car_reservations.py) `DomesticDetails`)
  - `welfare`: `subdistrict`, `district`, `province` (`WelfareDetails`)
  - ฟอร์มอยู่ที่ [forms/car_reservation.py](../../kampan/web/forms/car_reservation.py) และ template `form_domestic.html` / `form_welfare.html`
- พิมพ์เองเลยได้ค่าที่สะกดไม่ตรงกัน (`หาดใหญ่`, `อ.หาดใหญ่`, `หาดไหญ่`) ทำให้เอกสาร PDF และสถิติดูไม่เรียบร้อย

## แหล่งข้อมูล (จาก tent)

- ไฟล์ `~/tent/frontend/static/data/thailand_location_data.json` ขนาด 1.3 MB
  - มี 7,426 แถวแบบ flat: `{province, district, subdistrict, zipcode}`
  - รวมได้ 77 จังหวัด / 928 อำเภอ / 7,426 ตำบล
- tent serve ข้อมูลนี้ผ่าน `frontend/src/lib/server/thailand-location.ts` และ route `/api/v1/thailand-location/{provinces,districts,subdistricts,all}`
  - เรียงชื่อตามลำดับภาษาไทย
  - ปักหมุด **สงขลา** ไว้บนสุด และปักหมุด **หาดใหญ่** ไว้บนสุดเมื่อเลือกสงขลา
  - kampan จะใช้สัญญา API และการปักหมุดแบบเดียวกัน

## การตัดสินใจ

| เรื่อง | เลือก | เหตุผล |
|---|---|---|
| รูปแบบไฟล์ | **JSON** ไฟล์เดิมของ tent copy มาเลย | ไม่ต้องแปลงข้อมูล และตรงกับ tent ถ้าจะ sync ทีหลัง CSV ไม่ได้ช่วยอะไรเพิ่ม |
| ที่เก็บไฟล์ | `kampan/utils/data/thailand_location.json` (ฝั่ง server) | ไม่ต้องส่ง 1.3 MB ไปให้ browser โหลด browser ขอเฉพาะระดับที่ต้องใช้ผ่าน API |
| การโหลด | อ่านครั้งเดียวตอนเรียกครั้งแรก (`functools.cache`) แล้วสร้าง index `province → district → [subdistrict]` ไว้ใน memory | ข้อมูลไม่เปลี่ยน ไม่ต้องลง MongoDB |
| ที่เก็บค่าใน model | **ไม่เปลี่ยน** ยังเป็น `StringField` เก็บชื่อภาษาไทย | ไม่ต้อง migrate ข้อมูลเดิม PDF layout และ template รายละเอียดใช้ต่อได้เลย |
| การตรวจสอบค่า | เพิ่ม validator ในฟอร์ม: ชุด ต./อ./จ. ต้องมีอยู่จริงในชุดข้อมูล | กันค่าพิมพ์มั่วที่ถูกส่งผ่าน POST ตรง ๆ |
| UI | ใช้ `dropdown_select` ที่มีอยู่แล้ว (DaisyUI + ช่องค้นหา) ต่อกัน 3 ชั้น | ทำตาม skill daisyui-tailwind-bestpractices ไม่ต้องเพิ่ม library |

## API

Blueprint ใหม่: `kampan/web/views/thailand_location.py` → `Blueprint("thailand_location", url_prefix="/api/thailand-location")`
(`get_subblueprints` จะเจอไฟล์นี้และ register ให้เอง ต้องเพิ่มชื่อ blueprint ใน `NON_MODULE_BLUEPRINTS` และใน ACL ถ้า ACL บังคับ)

ทุก route ใช้ `@login_required` แต่ไม่ต้องจำกัดตาม organization เพราะเป็นข้อมูลอ้างอิงกลาง

| Method | Path | Query | Response |
|---|---|---|---|
| GET | `/api/thailand-location/provinces` | – | `["สงขลา", "กระบี่", ...]` |
| GET | `/api/thailand-location/districts` | `province` (ต้องมี) | `["หาดใหญ่", ...]` · ไม่มี province → 400 · ไม่พบ → `[]` |
| GET | `/api/thailand-location/subdistricts` | `province`, `district` (ต้องมีทั้งคู่) | `[{"subdistrict": "คอหงส์", "zipcode": 90110}, ...]` |

- ใส่ `Cache-Control: public, max-age=86400` เพราะข้อมูลไม่เปลี่ยน
- ตัด `/all` ของ tent ออก เพราะ kampan ไม่มีช่องค้นหารวมแบบในฟอร์ม household ของ tent

## ชั้น logic (`kampan/utils/thailand_location.py`)

```python
list_provinces() -> list[str]
list_districts(province) -> list[str]
list_subdistricts(province, district) -> list[dict]
is_valid(province, district=None, subdistrict=None) -> bool
```

- เรียงด้วย `pythainlp`/`icu` ถ้ามีใน dependency ถ้าไม่มีให้ sort ตาม Unicode ไปก่อน (ต้องเช็กว่าลำดับที่ได้รับได้หรือไม่)
- ปักหมุด สงขลา / หาดใหญ่ ไว้บนสุดเหมือน tent
- view เรียกแค่ฟังก์ชันพวกนี้ ฟอร์มก็เรียก `is_valid` ตัวเดียวกัน

## ฟอร์มและหน้าจอ

1. `DomesticRequestForm`: เปลี่ยน `province`, `district` เป็น `SelectField` แบบ `validate_choice=False` และเติม choices ฝั่ง server
   - จังหวัด: ใส่ครบทุกจังหวัด
   - อำเภอ: ใส่เฉพาะของจังหวัดที่เลือกอยู่ (ตอนแก้ไขหรือ re-render หลัง validate ไม่ผ่าน)
   - เพิ่ม `validate_district` ที่เรียก `is_valid`
2. `WelfareRequestForm`: ทำแบบเดียวกันทั้ง 3 ช่อง ลำดับบนจอเปลี่ยนเป็น **จังหวัด → อำเภอ → ตำบล** (ตอนนี้เรียง ต. → อ. → จ.)
   - ข้อความที่ประกอบเป็น `location` ยังเรียง `ต. อ. จ.` เหมือนเดิม
3. JS ใหม่ `kampan/web/static/js/forms/thailand_location_select.js`
   - หา container ที่มี `data-thai-location` ซึ่งมี `data-level="province|district|subdistrict"`
   - เมื่อเลือกจังหวัด → ล้างค่าอำเภอและตำบล → `fetch` districts → สร้าง option ใน dropdown ใหม่ → เปิดให้กดได้
   - เมื่อเลือกอำเภอ → ทำแบบเดียวกันกับตำบล
   - ระหว่างโหลดให้ปุ่ม disabled และแสดง `loading loading-spinner loading-xs`
   - ต้องเช็กว่า `dropdown_select.js` เปิด hook ให้ rebuild option ได้หรือไม่ ถ้าไม่มีให้เพิ่มฟังก์ชัน `setDropdownOptions(container, options)`
4. ข้อมูลเก่าที่พิมพ์เองและไม่ตรงชุดข้อมูล: ถ้าเปิดแก้ไข ให้ใส่ค่าเดิมเป็น option แรก พร้อมป้าย "(ค่าเดิม)" เพื่อไม่ให้ค่าหายไปเฉย ๆ แต่ถ้ากดบันทึกโดยไม่แก้ validator จะไม่ผ่าน และขึ้นข้อความให้เลือกใหม่
   - **ต้องให้ผู้ใช้ตัดสิน**: จะบังคับให้เลือกใหม่ หรือยอมให้ค่าเดิมผ่านไปได้

## Tests (`tests/test_thailand_location.py` และเพิ่มใน `tests/test_car_reservation.py`)

- `list_provinces()` ได้ 77 จังหวัด และ "สงขลา" อยู่ตัวแรก
- `list_districts("สงขลา")[0] == "หาดใหญ่"`
- `list_subdistricts("สงขลา", "หาดใหญ่")` มี "คอหงส์" พร้อม zipcode 90110
- API: ไม่ login → redirect · ไม่ส่ง province → 400 · ส่งจังหวัดที่ไม่มี → `[]`
- ฟอร์ม domestic/welfare: ชุดค่าที่ถูกต้องผ่าน · อำเภอไม่ตรงกับจังหวัดไม่ผ่าน
- browser check ตาม memory: คลิกเลือกจริง 3 ชั้นผ่าน Chrome CDP ทั้งบนมือถือและ desktop

## ลำดับงาน (micro commits)

1. `chore`: copy JSON จาก tent มาไว้ที่ `kampan/utils/data/` และเพิ่มใน package data ถ้า build เป็น wheel
2. `feat`: `utils/thailand_location.py` พร้อม unit tests
3. `feat`: blueprint API พร้อม tests
4. `feat`: JS สำหรับ dropdown ต่อกัน
5. `feat`: เปลี่ยนฟอร์ม domestic ให้ใช้ dropdown พร้อม validator
6. `feat`: เปลี่ยนฟอร์ม welfare ให้ใช้ dropdown พร้อม validator
7. browser check

## คำถามที่ต้องตอบก่อนเริ่ม

1. ข้อมูลเก่าที่ไม่ตรงชุดข้อมูล: จะบังคับให้เลือกใหม่ตอนแก้ไข หรือยอมให้ผ่าน
2. ฟอร์มอื่นนอก car_reservation (เช่น vehicle_lending หรือ snor_car) ต้องใช้ด้วยไหม ถ้าใช้ จะทำ macro `thai_location_fields()` กลางไว้ใน `html-renderer.html`
3. ต้องการ zipcode ไหม ตอนนี้ model ไม่มีช่องนี้ แต่ API ส่งค่ามาให้อยู่แล้ว
