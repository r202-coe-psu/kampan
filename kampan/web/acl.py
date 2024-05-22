from flask import redirect, url_for, request
from flask_login import current_user, LoginManager, login_url
from werkzeug.exceptions import Forbidden
from . import models

from functools import wraps

login_manager = LoginManager()


def init_acl(app):
    login_manager.init_app(app)

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
            # bypass admin to access any organization
            if "admin" in current_user.roles:
                return func(*args, **kwargs)

            try:
                organization_id = request.view_args["organization_id"]
            except:
                organization_id = request.args.get("organization_id")
            try:
                list_roles = list(roles)
                organization = models.Organization.objects.get(id=organization_id)

                for role in list_roles:
                    if role in current_user.get_current_organization_roles():
                        return func(*args, **kwargs)

                raise Forbidden()
            except:

                organization_roles = None
                raise Forbidden()
            if organization_roles:
                return func(*args, **kwargs)
            raise Forbidden()

        return wrapped

    return wrapper


@login_manager.user_loader
def load_user(user_id):
    user = models.User.objects.with_id(user_id)
    return user


@login_manager.unauthorized_handler
def unauthorized_callback():
    if request.method == "GET":
        response = redirect(login_url("accounts.login", request.url))
        return response

    return redirect(url_for("accounts.login"))
