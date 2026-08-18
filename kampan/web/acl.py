from functools import wraps

from flask import g, redirect, request, url_for
from flask_login import LoginManager, current_user
from werkzeug.exceptions import Forbidden

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
