import datetime
import pandas
from io import BytesIO
from flask_login import current_user
from flask import send_file
from kampan import models
from mongoengine import Q

MEMBER_HEADER = [
    "ชื่อ-นามสกุล (ภาษาไทย)",
    "ชื่อ-นามสกุล (ภาษากฤษ)",
    "Email",
    "ตำแหน่ง",
    "แผนก",
]


def validate_file(file, required_columns):
    try:
        df = pandas.read_excel(file)
    except Exception:
        return None, ["กรุณาอัปโหลดเอกสารโดยใช้ Excel Format 2007"]

    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        return None, [f"ไม่พบ {col} ในหัวตาราง" for col in missing_columns]

    return df, []


def validate_row_field(
    row,
    field_name,
    idx,
    error_list,
    validator=None,
    error_msg=None,
    validate_duplicate=True,
):
    value = row.get(field_name)
    if pandas.isnull(value) or (isinstance(value, str) and not value.strip()):
        error_list.append(f"ไม่พบ {field_name} ในบรรทัดที่ {idx+2} กรุณากรอกข้อมูล")
        return error_list

    if validate_duplicate:
        if validator and not validator(value):
            error_list.append(error_msg.format(value=value, idx=idx + 2))
            return error_list

    return error_list


def validate_member_upload_engagement(file, organization):
    df, errors = validate_file(file, MEMBER_HEADER)
    if errors:
        return errors

    for idx, row in df.iterrows():
        errors = validate_row_field(
            row,
            "Email",
            idx,
            errors,
            lambda email: models.OrganizationUserRole.objects(
                email=email.strip(),
                organization=organization,
                status__ne="disactive",
            ).first(),
            "ไม่พบพนักงานชื่อ {value} ในระบบ ในบรรทัดที่ {idx} กรุณาตรวจสอบข้อมูล",
            False,
        )
        errors = validate_row_field(
            row,
            "แผนก",
            idx,
            errors,
            lambda name: models.Division.objects(
                name=name.strip(),
                organization=organization,
                status__ne="disactive",
            ).first(),
            "ไม่พบแผนกชื่อ {value} ในระบบ ในบรรทัดที่ {idx} กรุณาตรวจสอบข้อมูล",
            False,
        )

    return errors


def process_member_upload_file(file, organization, current_user):
    df = pandas.read_excel(file)
    for idx, row in df.iterrows():
        user = models.User.objects(
            email=str(row.get("Email")).strip(),
            status__ne="disactive",
        ).first()

        member = None
        if user:
            member = models.OrganizationUserRole.objects(
                user=user,
                status__ne="disactive",
                organization=organization,
            ).first()
        else:
            member = models.OrganizationUserRole.objects(
                email=str(row.get("Email")).strip(),
                status__ne="disactive",
                organization=organization,
            ).first()

        if not member:
            member = models.OrganizationUserRole(
                organization=organization,
                roles=["staff"],
                added_by=current_user,
                last_modifier=current_user,
            )
        member.first_name = str(row.get("ชื่อ-นามสกุล (ภาษากฤษ)", "")).strip().split()[0]
        member.last_name = str(row.get("ชื่อ-นามสกุล (ภาษากฤษ)", "")).strip().split()[-1]
        member.email = str(row.get("Email", "")).strip()
        member.appointment = str(row.get("ตำแหน่ง", "")).strip()

        division = models.Division.objects(
            name=str(row.get("แผนก", "")).strip(),
            status__ne="disactive",
            organization=organization,
        ).first()
        if not division:
            division = models.Division(
                name=str(row.get("แผนก")).strip(),
                organization=organization,
                created_by=current_user,
                description="",
            )
            division.save()
        member.division = division
        member.save()
    return


def get_template_delete_items_file():
    df = pandas.DataFrame(columns=MEMBER_HEADER)
    excel_output = BytesIO()
    with pandas.ExcelWriter(excel_output) as writer:
        workbook = writer.book
        df.to_excel(writer, sheet_name="ข้อมูลสมาชิก", index=False)
        workbook.close()

    excel_output.seek(0)
    return send_file(
        excel_output,
        as_attachment=True,
        download_name="รูปแบบไฟล์การเพิ่มสมาชิก.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
