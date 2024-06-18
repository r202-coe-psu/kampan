from flask import g, config, session, redirect, url_for, current_app
from flask_login import current_user, login_user
from authlib.integrations.flask_client import OAuth

from .. import models
import mongoengine as me
import requests

import datetime


def fetch_token(name):
    token = models.OAuth2Token.objects(
        name=name, user=current_user._get_current_object()
    ).first()
    return token.to_dict()


def update_token(name, token):
    item = models.OAuth2Token(
        name=name, user=current_user._get_current_object()
    ).first()
    item.token_type = token.get("token_type", "Bearer")
    item.access_token = token.get("access_token")
    item.refresh_token = token.get("refresh_token")
    item.expires = datetime.datetime.utcfromtimestamp(token.get("expires_at"))

    item.save()
    return item


oauth2_client = OAuth()


def create_user_google(user_info, user=None):
    if not user:
        user = models.User(
            username=user_info.get("email"),
            picture_url=user_info.get("picture"),
            email=user_info.get("email"),
            first_name=user_info.get("given_name"),
            last_name=user_info.get("family_name"),
            status="active",
        )
    elif not user.resources:
        user.username = user_info.get("email")
        user.first_name = user_info.get("given_name", "").title()
        user.last_name = user_info.get("family_name", "").title()
        user.email = user_info.get("email")
        user.picture_url = user_info.get("picture")

    user.save()
    return user


def create_user_engpsu(user_info, user=None):
    if not user:
        user = models.User(
            username=user_info.get("username"),
            email=user_info.get("email"),
            first_name=user_info.get("first_name").title(),
            last_name=user_info.get("last_name").title(),
            status="active",
        )
    elif not user.resources:
        user.first_name = user_info.get("given_name", "").title()
        user.last_name = user_info.get("family_name", "").title()
        user.email = user_info.get("email")

    if "staff_id" in user_info.keys():
        user.roles.append("staff")
    elif "student_id" in user_info.keys():
        user.roles.append("student")

    if user_info["username"].isdigit():
        user.roles.append("student")
    else:
        user.roles.append("staff")

    user.save()
    return user


def create_user_psu(user_info, user=None):
    print(user_info)
    if not user:
        user = models.User(
            username=user_info.get("username"),
            email=user_info.get("email"),
            first_name=user_info.get("first_name").title(),
            last_name=user_info.get("last_name").title(),
            status="active",
        )
    elif not user.resources:
        user.first_name = user_info.get("first_name", "").title()
        user.last_name = user_info.get("last_name", "").title()
        user.email = user_info.get("email")

    user.save()

    if user_info["username"].isdigit():
        user.roles.append("student")
    else:
        user.roles.append("staff")

    if user_info.get("office_name"):
        organization_name = user_info.get("office_name").split(" ")[-1].strip()
        organization = models.Organization.objects(name=organization_name).first()
        if organization and organization not in user.organizations:
            # user.organizations.append(organization)
            organization_user_role = models.OrganizationUerRole(
                organization=organization,
                user=user,
            )
            organization_user_role.save()

        if not user.user_setting.current_organization:
            user.user_setting.current_organization = organization

    if user_info.get("full_name_th"):
        name_th = user_info.get("full_name_th").split(" ")
        user.first_name_th = name_th[0]
        user.last_name_th = name_th[-1]

    user.title_th = user_info.get("title_th")
    user.title = user_info.get("title")
    # user.other_ids.append(user_info.get("username"))

    user.save()
    return user


def create_user_line(user_info, user=None):
    name = user_info.get("name", "")
    names = ["", ""]
    if name:
        names = name.split(" ")
        if len(names) < 2:
            names.append("")

    if not user:
        user = models.User(
            username=user_info.get("email", name),
            subid=user_info.get("sub"),
            picture_url=user_info.get("picture"),
            email=user_info.get("email", ""),
            first_name=names[0],
            last_name=names[1],
            status="active",
        )
    elif not user.resources:
        user.username = user_info.get("email", name)
        user.subid.get("sub")
        user.picture_url = user_info.get("picture")
        user.email = user_info.get("email", "")
        user.first_name = names[0]
        user.last_name = names[1]

    user.save()
    return user


def create_user_facebook(user_info, user=None):
    if not user:
        user = models.User(
            username=user_info.get("email"),
            picture_url=f"http://graph.facebook.com/{user_info.get('sub')}/picture?type=large",
            email=user_info.get("email"),
            first_name=user_info.get("first_name"),
            last_name=user_info.get("last_name"),
            status="active",
        )
    elif not user.resources:
        user.picture_url = (
            f"http://graph.facebook.com/{user_info.get('sub')}/picture?type=large"
        )
        user.email = user_info.get("email")
        user.first_name = user_info.get("first_name")
        user.last_name = user_info.get("last_name")

    user.save()
    return user


def get_user_info(remote, token):
    userinfo = {}
    if remote.name == "google":
        userinfo = token["userinfo"]
    elif remote.name == "facebook":
        USERINFO_FIELDS = [
            "id",
            "name",
            "first_name",
            "middle_name",
            "last_name",
            "email",
            "website",
            "gender",
            "locale",
        ]
        USERINFO_ENDPOINT = "me?fields=" + ",".join(USERINFO_FIELDS)
        userinfo_response = remote.get(USERINFO_ENDPOINT)
        userinfo = userinfo_response.json()

    elif remote.name == "line":
        id_token = token.get("id_token")
        userinfo_response = requests.post(
            "https://api.line.me/oauth2/v2.1/verify",
            data={"id_token": str(id_token), "client_id": remote.client_id},
        )

        userinfo = userinfo_response.json()
    elif remote.name == "psu":
        AUTHLIB_SSL_VERIFY = current_app.config.get("AUTHLIB_SSL_VERIFY_PSU", False)
        # token = remote.authorize_access_token(verify=AUTHLIB_SSL_VERIFY)
        userinfo = token.get("userinfo")

        if not userinfo:
            userinfo_response = remote.get("userinfo", verify=AUTHLIB_SSL_VERIFY)
            userinfo = userinfo_response.json()

    elif remote.name == "engpsu":
        userinfo_response = remote.get("userinfo")
        userinfo = userinfo_response.json()

    return userinfo


def handle_authorized_oauth2(remote, token):
    user_info = get_user_info(remote, token)

    user = None
    if remote.name == "psu":
        user = models.User.objects(username=user_info.get("username")).first()
    elif "email" in user_info and user_info["email"]:
        user = models.User.objects(me.Q(email=user_info.get("email"))).first()
    elif "sub" in user_info:
        user = models.User.objects(subid=user_info.get("sub")).first()

    # print(remote.name, user, user_info.get("username"))

    if not user or not user.resources:
        if remote.name == "google":
            user = create_user_google(user_info)
        elif remote.name == "facebook":
            user = create_user_facebook(user_info)
        elif remote.name == "line":
            user = create_user_line(user_info)
        elif remote.name == "engpsu":
            user = create_user_engpsu(user_info, user)
        elif remote.name == "psu":
            user = create_user_psu(user_info)

    login_user(user)
    user.resources[remote.name] = user_info
    user.save()

    if token:
        oauth2token = models.OAuth2Token(
            name=remote.name,
            user=user,
            access_token=token.get("access_token"),
            token_type=token.get("token_type"),
            refresh_token=token.get("refresh_token", None),
            expires=datetime.datetime.utcfromtimestamp(token.get("expires_in")),
        )
        oauth2token.save()

    next_uri = session.get("next", None)
    if next_uri:
        session.pop("next")
        return redirect(next_uri)

    return redirect(url_for("accounts.index"))


def init_oauth(app):
    oauth2_client.init_app(app, fetch_token=fetch_token, update_token=update_token)

    oauth2_client.register("engpsu")
    oauth2_client.register("psu")
    oauth2_client.register("google")
