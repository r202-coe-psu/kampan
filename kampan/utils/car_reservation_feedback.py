from kampan import models

"""แบบประเมินความพึงพอใจของระบบจองรถ (spec ข้อ 5.6): คำถามตายตัวในโค้ด"""

# (key ของกลุ่ม, หัวข้อ, [(key ของคำถาม, ข้อความ), ...])
QUESTION_GROUPS = [
    (
        "vehicle",
        "สภาพรถยนต์",
        [
            ("vehicle_cleanliness", "ความสะอาด"),
            ("vehicle_suitability", "ความเหมาะสมของรถยนต์กับการเดินทาง"),
            ("vehicle_readiness", "ความพร้อม (น้ำมัน/สภาพเครื่องยนต์)"),
            ("vehicle_air_conditioning", "ระบบปรับอากาศ"),
        ],
    ),
    (
        "driver",
        "พนักงานขับรถยนต์",
        [
            ("driver_driving", "การขับขี่ (ความเร็ว/การปฏิบัติตามกฎจราจร)"),
            ("driver_punctuality", "การตรงต่อเวลา"),
            ("driver_route_study", "ศึกษาเส้นทางก่อนการเดินทาง"),
            ("driver_service_mind", "ความเอื้อเฟื้อ/มีจิตบริการ"),
        ],
    ),
    (
        "overall",
        "ความพึงพอใจในภาพรวม",
        [("overall", "ความพึงพอใจในภาพรวม")],
    ),
]

SCORE_QUESTIONS = [
    (key, text) for _, _, questions in QUESTION_GROUPS for key, text in questions
]
SCORE_KEYS = [key for key, _ in SCORE_QUESTIONS]
SCORE_MIN, SCORE_MAX = 1, 5


def can_submit(reservation, user):
    """เฉพาะผู้ขอของใบขอนั้น และเมื่อ พขร. ปิดงานแล้วเท่านั้น"""
    return reservation.status == "completed" and reservation.creator == user


def feedback_of(reservation):
    """ผลประเมินของใบขอ (None ถ้ายังไม่ประเมิน)"""
    return models.CarReservationFeedback.objects(reservation=reservation).first()


def state_for(reservation, user):
    """สถานะแบบประเมินของใบขอสำหรับผู้ดู: "available" (ประเมินได้), "done" (ประเมินแล้ว), None (ไม่เกี่ยว)"""
    if not can_submit(reservation, user):
        return None
    return "done" if feedback_of(reservation) is not None else "available"
