from functools import wraps

from flask import g, redirect, request, url_for
from flask_login import LoginManager, current_user
from werkzeug.exceptions import Forbidden, NotFound

from . import models

login_manager = LoginManager()


def get_requested_organization_id():
    if request.view_args and request.view_args.get("organization_id"):
        return request.view_args.get("organization_id")

    if request.args.get("organization_id"):
        return request.args.get("organization_id")

    if request.form and request.form.get("organization_id"):
        return request.form.get("organization_id")

    return None


# blueprint ที่อยู่ภายใต้โมดูลใด ถ้าองค์กรปิดโมดูลนั้น หน้าเหล่านี้ต้องเปิดไม่ได้
# คีย์เป็นชื่อเต็มของ blueprint หรือชื่อระดับบนสุด (เช่น "procurement" ครอบคลุม
# "procurement.requisitions" ทุกตัว) ส่วน account, site, organizations, admin
# ไม่อยู่ในรายการ จึงเปิดได้เสมอ
MODULE_OF_BLUEPRINT = {
    "vehicle_lending.car_applications": "car",
    "vehicle_lending.car_permissions": "car",
    "vehicle_lending.cars": "car",
    "vehicle_lending.car_tasks": "car",
    "vehicle_lending.car_feedback": "car",
    "vehicle_lending.car_manuals": "car",
    "vehicle_lending.history_car_lending": "car",
    "vehicle_lending.motorcycle_applications": "motorcycle",
    "vehicle_lending.motorcycle_permissions": "motorcycle",
    "vehicle_lending.motorcycles": "motorcycle",
    "vehicle_lending.motorcycle_manuals": "motorcycle",
    "snor_car": "snor_car",
    "procurement": "procurement",
    "items": "inventory",
    "item_orders": "inventory",
    "item_checkouts": "inventory",
    "item_positions": "inventory",
    "item_registers": "inventory",
    "inventories": "inventory",
    "warehouses": "inventory",
    "categories": "inventory",
    "suppliers": "inventory",
    "lost_breaks": "inventory",
    "approve_orders": "inventory",
    "dashboard": "inventory",
    "notifications": "inventory",
}


def module_of_blueprint(blueprint_name):
    if not blueprint_name:
        return None
    return MODULE_OF_BLUEPRINT.get(blueprint_name) or MODULE_OF_BLUEPRINT.get(
        blueprint_name.split(".")[0]
    )


def enforce_enabled_module():
    organization = getattr(g, "organization", None)
    if organization is None:
        return

    module_key = module_of_blueprint(request.blueprint)
    if module_key and not organization.has_module(module_key):
        raise NotFound()


def init_acl(app):
    login_manager.init_app(app)

    @app.before_request
    def resolve_viewing_organization():
        g.organization = None
        g.organization_denied = False

        if not current_user.is_authenticated:
            return

        organization_id = get_requested_organization_id()
        if not organization_id:
            # ตรวจสมาชิกภาพของหน่วยงานตั้งต้นด้วย เพราะค่าที่จำไว้ใน user_setting
            # อาจเป็นหน่วยงานที่ผู้ใช้ถูกนำออกไปแล้ว
            organization = current_user.get_default_organization()
            if organization and current_user.is_member_of(organization):
                g.organization = organization
            return

        try:
            organization = models.Organization.objects(id=organization_id).first()
        except Exception:
            organization = None

        if organization and current_user.is_member_of(organization):
            g.organization = organization
        else:
            g.organization_denied = True

    @app.before_request
    def gate_disabled_modules():
        enforce_enabled_module()

    @app.errorhandler(403)
    def page_not_found(e):
        return unauthorized_callback()


def roles_required(*roles):
    def wrapper(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                raise Forbidden()

            for role in roles:
                if role in current_user.roles:
                    return func(*args, **kwargs)
            raise Forbidden()

        return wrapped

    return wrapper


def organization_roles_required(*roles):
    def wrapper(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                raise Forbidden()

            # bypass admin
            if "admin" in current_user.roles:
                return func(*args, **kwargs)

            # ขอดูหน่วยงานที่ไม่ได้เป็นสมาชิก
            if getattr(g, "organization_denied", False):
                raise Forbidden()

            organization = getattr(g, "organization", None)
            if not organization:
                raise Forbidden()  # ไม่มีหน่วยงานให้ตรวจ

            # ตรวจ role ในหน่วยงานที่กำลังดูอยู่ ไม่ใช่หน่วยงานใดก็ได้ที่ผู้ใช้สังกัด
            user_roles = current_user.get_organization_roles(organization)

            if any(role in user_roles for role in roles):
                return func(*args, **kwargs)

            raise Forbidden()  # ไม่มี role ตรงกับที่กำหนดในหน่วยงานนี้

        return wrapped

    return wrapper


@login_manager.user_loader
def load_user(user_id):
    user = models.User.objects.with_id(user_id)
    return user


@login_manager.unauthorized_handler
def unauthorized_callback():
    if request.method == "GET":
        return redirect(url_for("accounts.login", next=request.url))

    return redirect(url_for("accounts.login"))
