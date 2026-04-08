from flask_wtf import FlaskForm, file
from flask_mongoengine.wtf import model_form
from wtforms import fields, Form, validators, TextAreaField, HiddenField, DecimalField

from kampan import models
from kampan.models.requisition_timeline import PROGRESS_STATUS_CHOICES

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


class ReservationPaymentForm(Form):
    reservation_id = HiddenField()
    amount = DecimalField(
        places=2,
        rounding=None,
        default=0,
        validators=[validators.NumberRange(min=0)],
    )


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
    serial_number = fields.StringField("เลขที่สินค้า", validators=[validators.Optional()])
    price_per_piece = fields.DecimalField(
        "ราคาต่อชิ้น", validators=[validators.Optional()]
    )


class CompletedForm(FlaskForm):
    requisition_code = fields.StringField(
        "เลขที่ มอ.เบิกจ่าย", render_kw={"readonly": True}
    )
    paid_date = fields.DateField("วันที่เบิกจ่าย", render_kw={"readonly": True})
    product_name = fields.StringField("ชื่อรายการ", render_kw={"readonly": True})
    total_amount = fields.StringField(
        "เงินทั้งหมดตามเลขที่ มอ เบิกจ่าย", render_kw={"readonly": True}
    )
    delivered_date = fields.DateField("วันที่ส่งของ", render_kw={"readonly": True})
    inspection_date = fields.DateField("วันที่ตรวจรับ", render_kw={"readonly": True})
    requisition_creator = fields.StringField(
        "ชื่อผู้เบิกครุภัณฑ์", render_kw={"readonly": True}
    )
    money_type = fields.SelectField(
        "ประเภทเงิน",
        validators=[validators.DataRequired()],
        choices=[
            ("งบประมาณ", "งบประมาณ"),
            ("รายได้", "รายได้"),
        ],
    )
    seller_name = fields.StringField("ชื่อผู้ขาย", validators=[validators.DataRequired()])
    contract_number = fields.StringField(
        "เลขที่สัญญา", validators=[validators.DataRequired()]
    )
    purchase_method = fields.StringField(
        "วิธีการจัดซื้อ",
        validators=[validators.DataRequired()],
    )
    start_warranty_date = fields.DateField(
        "วันที่เริ่มประกัน", validators=[validators.DataRequired()]
    )
    end_warranty_date = fields.DateField(
        "วันที่สิ้นสุดประกัน", validators=[validators.DataRequired()]
    )
    warranty_period = fields.IntegerField(
        "ระยะเวลาประกัน", validators=[validators.DataRequired()]
    )
    product_number = fields.StringField("เลขที่สินค้า", validators=[validators.Optional()])
    asset_code = fields.StringField("รหัสครุภัณฑ์", validators=[validators.DataRequired()])
    account_code = fields.StringField("รหัสบัญชี", validators=[validators.DataRequired()])
    usage_location = fields.StringField(
        "สถานที่ใช้งาน", validators=[validators.DataRequired()]
    )


class RequisitionTimelineItemForm(FlaskForm):
    class Meta:
        csrf = False

    requisition_timeline = HiddenField()
    requisition = HiddenField()
    requisition_item_id = HiddenField()
    # section ข้างบนตาราง
    insurance_start_date = fields.DateField(
        "วันที่เริ่มประกัน", validators=[validators.DataRequired()]
    )
    seller = fields.StringField("ชื่อผู้ขาย", validators=[validators.DataRequired()])
    insurance_end_date = fields.DateField(
        "วันที่สิ้นสุดประกัน", validators=[validators.DataRequired()]
    )
    # section ข้อมูลในตาราง
    responder_user = fields.SelectField(
        "ผู้รับผิดชอบ", validators=[validators.DataRequired()], choices=[]
    )
    serial_number = fields.StringField(
        "เลขที่สินค้า", validators=[validators.DataRequired()]
    )
    requisition_item_code = fields.StringField(
        "เลขที่ใบเบิก", validators=[validators.DataRequired()]
    )
    location = fields.StringField("สถานที่ใช้งาน", validators=[validators.DataRequired()])


class RequisitionTimelineItemSharedForm(FlaskForm):
    class Meta:
        csrf = False

    seller = fields.StringField("ชื่อผู้ขาย", validators=[validators.DataRequired()])
    insurance_start_date = fields.DateField(
        "วันที่เริ่มประกัน", validators=[validators.DataRequired()]
    )
    insurance_end_date = fields.DateField(
        "วันที่สิ้นสุดประกัน", validators=[validators.DataRequired()]
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
        "ราคาทั้งหมด (บาท)",
        places=2,
        rounding=None,
        validators=[validators.DataRequired(), validators.NumberRange(min=0)],
    )
    winner = fields.StringField("ผู้ชนะ", validators=[validators.Optional()])
    account_code = fields.StringField("ผังบัญชี", validators=[validators.Optional()])
    note = fields.StringField("หมายเหตุ", validators=[validators.Optional()])


class DetailsSpecifiedForm(FlaskForm):
    project_name = fields.StringField(
        "ชื่อโครงการ (ไม่บังคับใส่)", validators=[validators.Optional()]
    )
    items = fields.FieldList(fields.FormField(DetailsSpecifiedItemForm))
