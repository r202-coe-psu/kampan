from flask_wtf import FlaskForm, file
from flask_mongoengine.wtf import model_form
from wtforms import fields, Form, validators, TextAreaField, HiddenField, DecimalField

from kampan import models
from kampan.models.requisition_timeline import PROGRESS_STATUS_CHOICES

ACCOUNT_TYPE_CHOICES = [
    ("12030201 อาคารและสิ่งปลูกสร้าง", "12030201 อาคารและสิ่งปลูกสร้าง"),
    ("12030203 ส่วนปรับปรุงอาคาร", "12030203 ส่วนปรับปรุงอาคาร"),
    ("12030302 ครุภัณฑ์", "12030302 ครุภัณฑ์"),
    (
        "12030402 งานระหว่างก่อสร้าง-ที่ดิน อาคาร และอุปกรณ์",
        "12030402 งานระหว่างก่อสร้าง-ที่ดิน อาคาร และอุปกรณ์",
    ),
    ("1204010101 สินทรัพย์ไม่มีตัวตน", "1204010101 สินทรัพย์ไม่มีตัวตน"),
    ("12070101 ถนน", "12070101 ถนน"),
    (
        "12070201 สินทรัพย์โครงสร้างพื้นฐานอื่น",
        "12070201 สินทรัพย์โครงสร้างพื้นฐานอื่น",
    ),
    (
        "12070302 งานระหว่างก่อสร้าง-สินทรัพย์โครงสร้างพื้นฐาน",
        "12070302 งานระหว่างก่อสร้าง-สินทรัพย์โครงสร้างพื้นฐาน",
    ),
    ("51010208 งานเบี้ยประกันสุขภาพ", "51010208 งานเบี้ยประกันสุขภาพ"),
    (
        "51040102 ค่าใช้จ่ายด้านฝึกอบรม-ในประเทศ",
        "51040102 ค่าใช้จ่ายด้านฝึกอบรม-ในประเทศ",
    ),
    (
        "51040105 ค่าใช้จ่ายด้านฝึกอบรมบุคคลภายนอก",
        "51040105 ค่าใช้จ่ายด้านฝึกอบรมบุคคลภายนอก",
    ),
    ("51040301 ค่าซ่อมแซมและค่าบำรุงรักษา", "51040301 ค่าซ่อมแซมและค่าบำรุงรักษา"),
    (
        "5104040101 ค่าจ้างเหมาบริการ-บุคคลภายนอก",
        "5104040101 ค่าจ้างเหมาบริการ-บุคคลภายนอก",
    ),
    ("51040601 ค่าจ้างที่ปรึกษา", "51040601 ค่าจ้างที่ปรึกษา"),
    ("51040701 ค่าเบี้ยประกันภัย", "51040701 ค่าเบี้ยประกันภัย"),
    ("51040901 ค่ารับรองและพิธีการ", "51040901 ค่ารับรองและพิธีการ"),
    (
        "51041002 ค่าเช่าอสังหาริมทรัพย์-บุคคลภายนอก",
        "51041002 ค่าเช่าอสังหาริมทรัพย์-บุคคลภายนอก",
    ),
    ("51041004 ค่าเช่าเบ็ดเตล็ด-บุคคลภายนอก", "51041004 ค่าเช่าเบ็ดเตล็ด-บุคคลภายนอก"),
    ("51041101 ค่าประชาสัมพันธ์", "51041101 ค่าประชาสัมพันธ์"),
    ("51041301 ค่าเชื้อเพลิง", "51041301 ค่าเชื้อเพลิง"),
    ("51041306 เงินชดเชยค่างานสิ่งก่อสร้าง", "51041306 เงินชดเชยค่างานสิ่งก่อสร้าง"),
    ("5104130804 ค่าใช้สอยอื่นๆ", "5104130804 ค่าใช้สอยอื่นๆ"),
    ("5105010101 ค่าวัสดุ", "5105010101 ค่าวัสดุ"),
    ("51050102 ค่าครุภัณฑ์ต่ำกว่าเกณฑ์", "51050102 ค่าครุภัณฑ์ต่ำกว่าเกณฑ์"),
    ("51060101 ค่าไฟฟ้า", "51060101 ค่าไฟฟ้า"),
]

BaseRequisitionTimelineForm = model_form(
    models.RequisitionTimeline,
    FlaskForm,
    exclude=[
        "requisition",
        "purchaser",
        "updated_date",
        "updated_by",
        "created_date",
        "created_by",
        "status",
    ],
)


class RequisitionTimelineForm(BaseRequisitionTimelineForm):
    pass


class RequisitionCancelForm(FlaskForm):
    note = TextAreaField(
        "เหตุผลการยกเลิก",
        [validators.DataRequired(), validators.Length(max=500)],
    )


class RequisitionInspectionForm(FlaskForm):
    inspection_date = fields.DateField(
        "วันที่ตรวจรับ",
        [validators.DataRequired()],
    )


class RequisitionDeliveryForm(FlaskForm):
    delivery_date = fields.DateField(
        "วันที่ส่งมอบ",
        [validators.DataRequired()],
    )


class ReservationPaymentForm(Form):
    class Meta:
        csrf = False

    reservation_id = HiddenField()
    is_selected = fields.BooleanField("Is Selected", default=False)
    amount = DecimalField(
        places=2,
        rounding=None,
        default=0,
        validators=[validators.Optional(), validators.NumberRange(min=0)],
    )
    item_amount = fields.IntegerField(
        default=0,
        validators=[validators.Optional(), validators.NumberRange(min=0)],
    )


class BillingItemForm(Form):
    class Meta:
        csrf = False

    item_id = HiddenField()
    is_multi_source = fields.BooleanField("Multi source", default=False)
    source_id = fields.StringField("Source", validators=[validators.Optional()])
    single_amount = DecimalField(
        places=2,
        rounding=None,
        default=0,
        validators=[validators.Optional(), validators.NumberRange(min=0)],
    )
    single_qty = fields.IntegerField(
        default=0,
        validators=[validators.Optional(), validators.NumberRange(min=0)],
    )
    multi_sources = fields.FieldList(fields.FormField(ReservationPaymentForm))


class BillingForm(FlaskForm):
    purchase_method = fields.SelectField(
        "วิธีการจัดซื้อ",
        choices=[
            ("", "เลือกวิธีการจัดซื้อ"),
            ("specific", "วิธีเฉพาะเจาะจง"),
            ("selective", "วิธีคัดเลือก"),
            ("e_bidding", "วิธีประกวดราคาอิเล็กทรอนิกส์ (e-bidding)"),
        ],
        validators=[validators.DataRequired()],
    )
    quotation_winner = fields.StringField(
        "ผู้ชนะการเสนอราคา", validators=[validators.Optional()]
    )
    items = fields.FieldList(fields.FormField(BillingItemForm))


class RequisitionTimelineFilterForm(FlaskForm):
    requisition_code = fields.StringField(
        "เลขที่คำขอ", validators=[validators.Optional()]
    )
    progress = fields.SelectField(
        "เลือกสถานะปัจจุบัน",
        choices=[("", "สถานะทั้งหมด")] + PROGRESS_STATUS_CHOICES,
    )


class MasForm(FlaskForm):
    mas_year = fields.IntegerField("ปีงบประมาณ", validators=[validators.Optional()])
    mas_code = fields.StringField("รหัสแหล่งเงิน", validators=[validators.Optional()])


class ItemListForm(FlaskForm):
    product_name = fields.StringField("ชื่อสินค้า", validators=[validators.Optional()])
    serial_number = fields.StringField(
        "เลขที่สินค้า", validators=[validators.Optional()]
    )
    price_per_piece = fields.DecimalField(
        "ราคาต่อชิ้น", validators=[validators.Optional()]
    )


class CompletedForm(FlaskForm):
    # Row 1
    year = fields.StringField("ปีงบประมาณ", render_kw={"readonly": True})
    mas_code = fields.StringField("รหัสงบประมาณ", render_kw={"readonly": True})

    # Row 2
    requisition_creator = fields.StringField(
        "ชื่อผู้ขอซื้อ/ขอจ้าง", render_kw={"readonly": True}
    )
    product_name = fields.StringField("ชื่อโครงการ", render_kw={"readonly": True})

    # Row 3
    contract_number = fields.StringField(
        "เลขที่สัญญา/ใบสั่งซื้อ", validators=[validators.Optional()]
    )
    delivery_period = fields.IntegerField(
        "กำหนดส่งมอบ(วัน)", validators=[validators.Optional()]
    )
    delivery_due_date = fields.DateField(
        "วันที่ครบกำหนดส่งมอบ", validators=[validators.Optional()]
    )

    # Row 4
    delivered_date = fields.DateField("วันที่ส่งมอบ", render_kw={"readonly": True})
    inspection_date = fields.DateField("วันที่ตรวจรับ", render_kw={"readonly": True})

    # Row 5
    requisition_code = fields.StringField(
        "เลขที่ มอ เบิกจ่าย", validators=[validators.Optional()]
    )
    paid_date = fields.DateField("วันที่เบิกจ่าย", validators=[validators.Optional()])
    total_amount = fields.StringField(
        "จำนวนเงินที่จ่ายจริง", render_kw={"readonly": True}
    )

    # Row 6
    receipt_number = fields.StringField(
        "เลขที่ใบแจ้งหนี้/ใบเสร็จ", validators=[validators.Optional()]
    )
    account_code = fields.StringField("ผังบัญชี", render_kw={"readonly": True})


class RequisitionTimelineItemForm(FlaskForm):
    class Meta:
        csrf = False

    requisition_timeline = HiddenField()
    requisition = HiddenField()
    requisition_item_id = HiddenField()
    # section ข้างบนตาราง
    insurance_start_date = fields.DateField(
        "วันที่เริ่มประกัน", validators=[validators.Optional()]
    )
    seller = fields.StringField("ชื่อผู้ขาย", validators=[validators.Optional()])
    insurance_end_date = fields.DateField(
        "วันที่สิ้นสุดประกัน", validators=[validators.Optional()]
    )
    # section ข้อมูลในตาราง
    responder_user = fields.SelectField(
        "ผู้รับผิดชอบ", validators=[validators.Optional()], choices=[]
    )
    serial_number = fields.StringField(
        "เลขที่สินค้า", validators=[validators.Optional()]
    )
    requisition_item_code = fields.StringField(
        "เลขที่ใบเบิก", validators=[validators.Optional()]
    )
    location = fields.StringField("สถานที่ใช้งาน", validators=[validators.Optional()])


class RequisitionTimelineItemSharedForm(FlaskForm):
    class Meta:
        csrf = False

    seller = fields.StringField("ชื่อผู้ขาย", validators=[validators.Optional()])
    insurance_start_date = fields.DateField(
        "วันที่เริ่มประกัน", validators=[validators.Optional()]
    )
    insurance_end_date = fields.DateField(
        "วันที่สิ้นสุดประกัน", validators=[validators.Optional()]
    )
    insurance_duration = fields.StringField(
        "ระยะเวลาประกัน",
        validators=[validators.Optional()],
        render_kw={"readonly": True},
    )


class DetailsSpecifiedItemForm(FlaskForm):
    class Meta:
        csrf = False

    item_id = HiddenField()
    product_name = fields.StringField(
        "ชื่อรายการ", validators=[validators.DataRequired()]
    )
    brand = fields.StringField("ยี่ห้อ", validators=[validators.Optional()])
    model_name = fields.StringField("รุ่น", validators=[validators.Optional()])
    quantity = fields.IntegerField(
        "จำนวน", validators=[validators.DataRequired(), validators.NumberRange(min=1)]
    )
    amount = fields.DecimalField(
        "ราคาต่อหน่วย (บาท)",
        places=2,
        rounding=None,
        validators=[validators.DataRequired(), validators.NumberRange(min=0)],
    )
    winner = fields.StringField("ผู้ชนะ", validators=[validators.Optional()])
    account_code = fields.SelectField(
        "ผังบัญชี", validators=[validators.Optional()], choices=ACCOUNT_TYPE_CHOICES
    )
    note = fields.StringField("หมายเหตุ", validators=[validators.Optional()])


class DetailsSpecifiedForm(FlaskForm):
    project_name = fields.StringField(
        "ชื่อโครงการ (ถ้ามี)", validators=[validators.Optional()]
    )
    items = fields.FieldList(fields.FormField(DetailsSpecifiedItemForm))
