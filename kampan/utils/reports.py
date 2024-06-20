import datetime
import pandas
from io import BytesIO
from flask_login import current_user
from flask import send_file
from kampan import models


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


def get_all_report(items_snapshot, organization):
    today = datetime.datetime.now()

    data = [
        [f"รายงานวัสดุคงเหลือเงิน ณ วันที่{today.day}/{today.month}/{today.year+543}"],
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
    print(description_data)
    description = pandas.DataFrame(description_data)

    excel_output = BytesIO()
    with pandas.ExcelWriter(excel_output) as writer:
        workbook = writer.book

        df.to_excel(
            writer,
            sheet_name=f"วัสดุคงเหลือวันที่{today.day}-{today.month}-{today.year+543}",
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
        download_name=f"all-report-{today.day}-{today.month}-{today.year+543}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    return response


def get_item_report(start_date, end_date, organization):
    df = pandas.DataFrame(data)
    today = datetime.datetime.now()
    excel_output = BytesIO()
    with pandas.ExcelWriter(excel_output) as writer:
        workbook = writer.book

        df.to_excel(
            writer,
            sheet_name=f"วันที่{today.day}-{today.month}-{today.year+543}",
            index=False,
            header=False,
        )

        workbook.close()

    excel_output.seek(0)
    response = send_file(
        excel_output,
        as_attachment=True,
        download_name=f"item-report-{today.day}-{today.month}-{today.year+543}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    return response
