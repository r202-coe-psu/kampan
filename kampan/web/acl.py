from flask import redirect, url_for, request
from flask_login import current_user, LoginManager, login_url
from flask_principal import Principal, identity_loaded, Identity, UserNeed, RoleNeed
from werkzeug.exceptions import Forbidden
from . import models

from functools import wraps

login_manager = LoginManager()
principals = Principal()


def init_acl(app):
    login_manager.init_app(app)

    @app.errorhandler(403)
    def page_not_found(e):
        return unauthorized_callback()


def roles_requred(roles):
    def wrapper(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            for role in roles:
                if role in current_user.roles:
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


@principals.identity_loader
def load_identity_when_session_expires():
    if hasattr(current_user, "id"):
        return Identity(current_user)


@identity_loaded.connect
def on_identity_loaded(sender, identity):
    # Set the identity user object
    identity.user = current_user

    # Add the UserNeed to the identity
    if hasattr(current_user, "id"):
        identity.provides.add(UserNeed(current_user.id))

    # Assuming the User model has a list of roles, update the
    # identity with the roles that the user provides
    if hasattr(current_user, "roles"):
        for role in current_user.roles:
            identity.provides.add(RoleNeed(role))
