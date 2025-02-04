import datetime
import pandas
from io import BytesIO
from flask_login import current_user
from flask import send_file
from kampan import models
from mongoengine import Q

REPORT_HEADER = [
    "ลำดับ",
    "ชื่อวัสดุ",
    "หมวดหมู่",
    "คงเหลือ (หน่วยนับใหญ่)",
    "หน่วยนับใหญ่",
    "คงเหลือ (หน่วยนับเล็ก)",
    "หน่วยนับเล็ก",
    "ราคาหน่วยใหญ่",
    "ราคาหน่วยเล็ก",
    "รวมเป็นเงิน",
]


def get_all_report(
    items_snapshot, organization, start_date=None, end_date=None, search_quarter=None
):
    if search_quarter:
        year, quarter = str(search_quarter).split("_")
        data = [
            [f"รายงานวัสดุคงเหลือเงิน ปีงบประมาณ {int(year) + 543 +1} ไตรมาสที่ {quarter}"],
            [organization.name],
            ["ลำดับ", "ชื่อวัสดุ", "คงเหลือ", "หน่วยนับ", "ราคาหน่วย", "เป็นเงิน"],
        ]
    elif start_date and end_date:
        data = [
            [
                f"รายงานวัสดุคงเหลือเงิน {start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')}"
            ],
            [organization.name],
            ["ลำดับ", "ชื่อวัสดุ", "คงเหลือ", "หน่วยนับ", "ราคาหน่วย", "เป็นเงิน"],
        ]
    else:
        data = [
            [f"รายงานวัสดุคงเหลือเงิน"],
            [organization.name],
            ["ลำดับ", "ชื่อวัสดุ", "คงเหลือ", "หน่วยนับ", "ราคาหน่วย", "เป็นเงิน"],
        ]
    all_remaining_balance = 0
    item_snapshot_by_category = {}

    for item_snapshot in items_snapshot:
        if item_snapshot.item.categories.name in item_snapshot_by_category.keys():
            item_snapshot_by_category[item_snapshot.item.categories.name].append(
                item_snapshot
            )
        else:
            item_snapshot_by_category[item_snapshot.item.categories.name] = [
                item_snapshot
            ]
    sorted_item_snapshot_by_category = {}
    for key in item_snapshot_by_category:
        sorted_item_snapshot_by_category[key] = sorted(
            item_snapshot_by_category[key], key=lambda x: x.item.name, reverse=False
        )
    item_snapshot_by_category = sorted_item_snapshot_by_category
    count = 1
    if item_snapshot_by_category:
        for k in item_snapshot_by_category.keys():
            data.append(["", k])
            for v in item_snapshot_by_category[k]:
                data.append(
                    [
                        count,
                        v.item.name,
                        (
                            v.amount_pieces
                            if v.item.item_format == "one to many"
                            else v.amount
                        ),
                        (
                            v.item.piece_unit
                            if v.item.item_format == "one to many"
                            else v.item.set_unit
                        ),
                        v.last_price_per_piece if v.last_price_per_piece else "-",
                        v.remaining_balance if v.remaining_balance else "-",
                    ]
                )
                if v.remaining_balance:
                    all_remaining_balance += v.remaining_balance
                count += 1
    data.append(["", "", "", "", "ยอดเงินคงเหลือ", all_remaining_balance])
    description_data = {}
    sort_items_snapshot = []
    for value in item_snapshot_by_category.values():
        sort_items_snapshot += value
    for column in REPORT_HEADER:
        description_data[column] = []
    count = 1
    for item_snapshot in sort_items_snapshot:
        description_data[REPORT_HEADER[0]].append(count)
        description_data[REPORT_HEADER[1]].append(item_snapshot.item.name)
        description_data[REPORT_HEADER[2]].append(item_snapshot.item.categories.name)
        description_data[REPORT_HEADER[3]].append(item_snapshot.amount)
        description_data[REPORT_HEADER[4]].append(item_snapshot.item.set_unit)
        description_data[REPORT_HEADER[5]].append(
            item_snapshot.get_amount_pieces()
            if item_snapshot.item.item_format == "one to many"
            else ""
        )
        description_data[REPORT_HEADER[6]].append(
            item_snapshot.item.piece_unit
            if item_snapshot.item.item_format == "one to many"
            else ""
        )
        description_data[REPORT_HEADER[7]].append(
            item_snapshot.last_price if item_snapshot.last_price else ""
        )
        description_data[REPORT_HEADER[8]].append(
            (
                item_snapshot.last_price_per_piece
                if item_snapshot.last_price_per_piece
                else ""
            )
            if item_snapshot.item.item_format == "one to many"
            else ""
        )
        description_data[REPORT_HEADER[9]].append(
            item_snapshot.remaining_balance if item_snapshot.remaining_balance else ""
        )
        count += 1
    df = pandas.DataFrame(data)
    description = pandas.DataFrame(description_data)

    excel_output = BytesIO()
    with pandas.ExcelWriter(excel_output) as writer:
        workbook = writer.book

        df.to_excel(
            writer,
            sheet_name=f"วัสดุคง",
            index=False,
            header=False,
        )
        description.to_excel(
            writer,
            sheet_name=f"รายละเอียดวัสดุคงเหลือ",
            index=False,
        )

        workbook.close()

    excel_output.seek(0)
    response = send_file(
        excel_output,
        as_attachment=True,
        download_name=f"all-report.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    return response


def get_item_report(start_date, end_date, organization):
    items = models.Item.objects(organization=organization, status="active").order_by(
        "name"
    )

    today = datetime.datetime.now()
    excel_output = BytesIO()
    with pandas.ExcelWriter(excel_output) as writer:
        workbook = writer.book
        for item in items:
            item_snapshot = (
                models.ItemSnapshot.objects(
                    Q(created_date__gte=start_date)
                    & Q(created_date__lt=end_date + datetime.timedelta(days=1))
                    & Q(status="active")
                    & Q(item=item)
                    & Q(organization=organization)
                )
                .order_by("created_date")
                .first()
            )
            inventories = models.Inventory.objects(
                Q(created_date__gte=start_date)
                & Q(created_date__lt=end_date + datetime.timedelta(days=1))
                & Q(status="active")
                & Q(item=item)
                & Q(organization=organization)
            )
            item_checkouts = models.CheckoutItem.objects(
                Q(created_date__gte=start_date)
                & Q(created_date__lt=end_date + datetime.timedelta(days=1))
                & Q(item=item)
                & Q(status="active")
                & Q(organization=organization)
            )
            lost_break_items = models.LostBreakItem.objects(
                Q(created_date__gte=start_date)
                & Q(created_date__lt=end_date + datetime.timedelta(days=1))
                & Q(status="active")
                & Q(item=item)
                & Q(organization=organization)
            )

            data = (
                ([item_snapshot] if item_snapshot else [])
                + list(item_checkouts)
                + list(inventories)
                + list(lost_break_items)
            )

            data = sorted(data, key=lambda el: el["created_date"])
            list_data = []
            amount_item = 0
            for row in data:
                if row._cls == "ItemSnapshot":
                    amount_item = (
                        row.amount_pieces
                        if row.item.item_format == "one to many"
                        else row.amount
                    )
                elif row._cls == "CheckoutItem":
                    amount_item -= row.quantity
                elif row._cls == "Inventory":
                    amount_item += row.quantity
                elif row._cls == "LostBreakItem":
                    amount_item -= row.quantity

                list_data.append((row, amount_item))
            count = 0
            loop_index = []
            date = []
            operation = []
            supplier = []
            amount = []
            unit = []
            price = []
            all_price = []
            remain = []
            for row, amount_item in list_data:
                count += 1
                loop_index.append(count)
                date.append(row.created_date.strftime("%d/%m/%Y"))
                remain.append(amount_item)
                unit.append(
                    row.item.piece_unit
                    if row.item.item_format == "one to many"
                    else row.item.set_unit
                )
                if row._cls == "ItemSnapshot":
                    operation.append("ยกยอด")
                    supplier.append("")
                    amount.append(
                        row.amount_pieces
                        if row.item.item_format == "one to many"
                        else row.amount
                    )
                    price.append(
                        row.last_price_per_piece if row.last_price_per_piece else "-"
                    )
                    all_price.append(
                        row.remaining_balance if row.remaining_balance else "-"
                    )
                elif row._cls == "CheckoutItem":
                    operation.append(f"เบิกโดย {row.user.get_name()}")
                    supplier.append("")
                    amount.append(f"-{row.quantity}")
                    price.append(row.item.get_last_price_per_piece())
                    all_price.append(f"-{row.get_all_price()}")
                elif row._cls == "Inventory":
                    operation.append(f"เติมวัสดุ")
                    supplier.append(row.registration.supplier.get_supplier_name())
                    amount.append(row.quantity)
                    price.append(row.item.get_last_price_per_piece())
                    all_price.append(f"{row.get_all_price()}")
                elif row._cls == "LostBreakItem":
                    operation.append(f"ชำรุด {row.description}")
                    supplier.append("")
                    amount.append(f"-{row.quantity}")
                    price.append(row.item.get_last_price_per_piece())
                    all_price.append(f"-{row.get_all_price()}")
            dataframe_item = {
                "ลำดับ": loop_index,
                "วันที่": date,
                "การดำเนินการ": operation,
                "ร้าน": supplier,
                "หน่วยนับ": unit,
                "ราคาต่อหน่วย": price,
                "เป็นเงิน": all_price,
                "คงเหลือ": remain,
            }
            df = pandas.DataFrame(dataframe_item)
            df.to_excel(
                writer,
                sheet_name=f"{item.name}",
                index=False,
            )

        workbook.close()

    excel_output.seek(0)
    start = f"{start_date.day}-{start_date.month}-{start_date.year}"
    end = f"{end_date.day}-{end_date.month}-{end_date.year}"
    response = send_file(
        excel_output,
        as_attachment=True,
        download_name=f"item-report-{start}-to-{end}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    return response
