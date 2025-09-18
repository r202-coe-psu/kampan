from typing import Optional
from kampan import models
from bson import ObjectId
import pandas as pd
import pathlib
from io import BytesIO
from flask import (
    send_file,
)
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    KeepTogether,
)
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


class HistoryCarLendingRepository:
    @staticmethod
    def get_export_car_applications(
        car_applications: list[models.vehicle_applications.CarApplication] = [],
    ):
        # แปลงเป็น list ของ dict
        data = []
        for idx, car_application in enumerate(car_applications, start=1):
            data.append(
                {
                    "ลำดับ": idx,
                    "วันที่ออกเดินทาง": car_application.departure_datetime.strftime(
                        "%d-%m-%Y %H:%M"
                    ),
                    "ผู้ขอใช้": car_application.creator.get_name(),
                    "ลักษณะงาน": car_application.request_reason,
                    "สถานที่ไป": car_application.location,
                    "กลับถึงเวลา": (
                        car_application.return_datetime.strftime("%d-%m-%Y %H:%M")
                        if car_application.return_datetime
                        else ""
                    ),
                    "เลขไมล์ก่อนเดินทาง": car_application.get_mile_before(),
                    "เลขไมล์หลังเดินทาง": car_application.last_mileage,
                }
            )

        # สร้าง DataFrame
        df = pd.DataFrame(data)

        # เขียนไฟล์ excel ลง memory
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="CarApplications")

        output.seek(0)
        return send_file(
            output,
            as_attachment=True,
            download_name="บันทึกการใช้รถยนต์.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @staticmethod
    def get_export_car_applications_pdf(
        car_applications: list[models.vehicle_applications.CarApplication],
        current_user: models.users.User = None,
        car: models.vehicles.Car = None,
    ):
        buffer = BytesIO()
        BASE_DIR = pathlib.Path(__file__).parent.parent
        FONT_DIR = BASE_DIR / "web" / "static" / "fonts"
        pdfmetrics.registerFont(TTFont("THSarabunNew", FONT_DIR / "THSarabunNew.ttf"))
        pdfmetrics.registerFont(
            TTFont("THSarabunNew-Bold", FONT_DIR / "THSarabunNew Bold.ttf")
        )

        buffer = BytesIO()
        inch = 72  # 1 นิ้ว = 72 points

        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=inch,
            rightMargin=inch,
            topMargin=inch,
            bottomMargin=inch,
        )
        styles = getSampleStyleSheet()
        styles["Title"].fontName = "THSarabunNew-Bold"
        styles["Normal"].fontName = "THSarabunNew"
        styles["Normal"].fontSize = 16
        elements = []

        # หัวรายงาน
        title = Paragraph("บันทึกการใช้รถยนต์ราชการ", styles["Title"])
        elements.append(title)
        elements.append(
            Paragraph(
                f"รถหมายเลขทะเบียน {car.license_plate}" if car else "รถหมายเลขทะเบียน",
                styles["Normal"],
            )
        )
        elements.append(Spacer(1, 12))
        elements.append(Spacer(1, 12))
        cell_style_center = ParagraphStyle(
            name="cell_center",
            fontName="THSarabunNew",
            fontSize=14,
            leading=16,
            alignment=TA_CENTER,
            wordWrap="CJK",
        )

        cell_style_left = ParagraphStyle(
            name="cell_left",
            fontName="THSarabunNew",
            fontSize=14,
            leading=16,
            alignment=TA_LEFT,
            wordWrap="CJK",
        )
        # หัวตาราง (ตามแบบราชการในภาพ)
        data = [
            [
                Paragraph("ลำดับ", cell_style_center),
                Paragraph("วันที่ออก เดินทาง", cell_style_center),
                Paragraph("เวลา ออก", cell_style_center),
                Paragraph("เลขไมล์ ก่อน", cell_style_center),
                Paragraph("ผู้ขอใช้", cell_style_center),
                Paragraph("ลักษณะงาน", cell_style_center),
                Paragraph("สถานที่ไป", cell_style_center),
                Paragraph("วันที่กลับ", cell_style_center),
                Paragraph("เวลา กลับ", cell_style_center),
                Paragraph("เลขไมล์ หลัง", cell_style_center),
            ]
        ]

        # เติมข้อมูล

        # เติมข้อมูล
        for idx, c in enumerate(car_applications, start=1):
            dep_date = c.departure_datetime.strftime("%d/%m/%y")
            dep_time = c.departure_datetime.strftime("%H:%M")
            ret_date = (
                c.return_datetime.strftime("%d/%m/%y") if c.return_datetime else ""
            )
            ret_time = c.return_datetime.strftime("%H:%M") if c.return_datetime else ""

            data.append(
                [
                    Paragraph(str(idx), cell_style_center),
                    Paragraph(dep_date, cell_style_center),
                    Paragraph(dep_time, cell_style_center),
                    Paragraph(str(c.get_mile_before()), cell_style_center),
                    Paragraph(str(c.creator.get_name()).split()[0], cell_style_left),
                    Paragraph(c.request_reason, cell_style_left),
                    Paragraph(c.location, cell_style_left),
                    Paragraph(ret_date, cell_style_center),
                    Paragraph(ret_time, cell_style_center),
                    Paragraph(str(c.last_mileage), cell_style_center),
                ]
            )
        # สร้างตาราง + กำหนดความกว้างคอลัมน์
        table = Table(
            data,
            repeatRows=1,
            # ลำดับ, วันที่ออกเดินทาง, เวลาออก, เลขไมล์ก่อน, ผู้ขอใช้, ลักษณะงาน, สถานที่ไป, วันที่กลับ, เวลากลับ, เลขไมล์หลัง
            colWidths=[35, 50, 35, 50, 60, 100, 80, 50, 35, 50],
        )

        # สไตล์ตาราง
        table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "THSarabunNew"),
                    ("FONTSIZE", (0, 0), (-1, -1), 14),
                    ("ALIGN", (0, 0), (0, -1), "CENTER"),  # ลำดับ
                    ("ALIGN", (1, 0), (2, -1), "CENTER"),  # วันที่/เวลา
                    ("ALIGN", (7, 0), (8, -1), "CENTER"),  # วันที่/เวลา กลับ
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                    ("ROWHEIGHT", (0, 0), (-1, -1), 22),
                ]
            )
        )

        elements.append(table)
        elements.append(Spacer(1, 12))

        normal_style = ParagraphStyle(
            "Normal",
            fontName="THSarabunNew",
            fontSize=16,
            leading=20,
        )
        right_style = ParagraphStyle(
            "Right",
            parent=normal_style,
            alignment=TA_RIGHT,
        )

        # ชื่อผู้เซ็น
        position = (
            f"{current_user.get_current_organization_user_role().appointment}".replace(
                " ", "_"
            )
            if current_user.get_current_organization_user_role()
            else "____________________________"
        )

        name = (
            f"{current_user.get_name()}".replace(" ", "_")
            if current_user
            else "____________________________"
        )

        appointment = position.center(len("____________________________"), "_")
        full_name = name.center(len("____________________________"), "_")

        elements.append(
            KeepTogether(
                [
                    Paragraph("ข้าพเจ้าขอรับรองความถูกต้องของข้อมูลดังกล่าว", right_style),
                    Spacer(1, 0.5 * inch),
                    Paragraph(
                        "......................................................",
                        right_style,
                    ),
                    Spacer(1, 12),
                    Paragraph(f"ชื่อ-สกุล: {full_name}", right_style),
                    Spacer(1, 12),
                    Paragraph(f"ตำแหน่ง: {appointment}", right_style),
                    Spacer(1, 0.2 * inch),
                    Paragraph("วันที่: ____/____/________", right_style),
                ]
            )
        )
        doc.build(elements)
        buffer.seek(0)
        return send_file(
            buffer,
            as_attachment=True,
            download_name="บันทึกการใช้รถยนต์.pdf",
            mimetype="application/pdf",
        )
