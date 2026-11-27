"""API ข้อมูลอ้างอิง จังหวัด / อำเภอ / ตำบล สำหรับ dropdown ต่อกันในฟอร์ม (ข้อมูลกลาง ไม่ผูกหน่วยงาน)"""

from flask import Blueprint, jsonify, request
from flask_login import login_required

from kampan.utils import thailand_location

module = Blueprint("thailand_location", __name__, url_prefix="/api/thailand-location")

CACHE_SECONDS = 24 * 60 * 60


def _cached(payload):
    response = jsonify(payload)
    response.headers["Cache-Control"] = f"private, max-age={CACHE_SECONDS}"
    return response


def _missing(*names):
    return jsonify({"error": f"ต้องระบุ {', '.join(names)}"}), 400


@module.route("/provinces")
@login_required
def provinces():
    return _cached(thailand_location.list_provinces())


@module.route("/districts")
@login_required
def districts():
    province = request.args.get("province", "").strip()
    if not province:
        return _missing("province")
    return _cached(thailand_location.list_districts(province))


@module.route("/subdistricts")
@login_required
def subdistricts():
    province = request.args.get("province", "").strip()
    district = request.args.get("district", "").strip()
    if not province or not district:
        return _missing("province", "district")
    return _cached(thailand_location.list_subdistricts(province, district))
