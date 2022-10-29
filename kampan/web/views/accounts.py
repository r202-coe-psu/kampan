import datetime
import markdown
import mongoengine as me

from flask import (
    Blueprint,
    render_template,
    url_for,
    redirect,
    request,
    session,
    current_app,
    send_file,
    abort,
)
from flask_login import login_user, logout_user, login_required, current_user

from .. import models
from .. import oauth2
from .. import acl
from .. import forms

module = Blueprint("accounts", __name__)


def get_user_and_remember():
    client = oauth2.oauth2_client
    result = client.principal.get("me")
    data = result.json()

    user = models.User.objects(
        me.Q(username=data.get("username", "")) | me.Q(email=data.get("email", ""))
    ).first()
    if not user:
        user = models.User(
            id=data.get("id"),
            first_name=data.get("first_name").title(),
            last_name=data.get("last_name").title(),
            email=data.get("email"),
            username=data.get("username"),
            status="active",
        )
        roles = []
        for role in ["student", "lecturer", "staff"]:
            if role in data.get("roles", []):
                roles.append(role)

        user.save()

    if user:
        login_user(user, remember=True)


@module.route("/login", methods=("GET", "POST"))
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if "next" in request.args:
        session["next"] = request.args.get("next", None)

    return render_template("/accounts/login.html")


@module.route("/login-engpsu")
def login_engpsu():
    client = oauth2.oauth2_client
    scheme = request.environ.get("HTTP_X_FORWARDED_PROTO", "http")
    redirect_uri = url_for("accounts.authorized_engpsu", _external=True, _scheme=scheme)
    response = client.engpsu.authorize_redirect(redirect_uri)
    return response


@module.route("/authorized-engpsu")
def authorized_engpsu():
    client = oauth2.oauth2_client
    try:
        token = client.engpsu.authorize_access_token()
    except Exception as e:
        print(e)
        return redirect(url_for("accounts.login"))

    userinfo_response = client.engpsu.get("userinfo")
    userinfo = userinfo_response.json()

    user = models.User.objects(
        me.Q(username=userinfo.get("username", ""))
        | me.Q(email=userinfo.get("email", ""))
    ).first()

    if not user:
        user = models.User(
            username=userinfo.get("username"),
            email=userinfo.get("email"),
            first_name=userinfo.get("first_name").title(),
            last_name=userinfo.get("last_name").title(),
            status="active",
        )
        user.resources[client.engpsu.name] = userinfo
        # if 'staff_id' in userinfo.keys():
        #     user.roles.append('staff')
        # elif 'student_id' in userinfo.keys():
        #     user.roles.append('student')
        if userinfo["username"].isdigit():
            user.roles.append("student")
        elif (
            "COE_LECTURERS" in current_app.config
            and userinfo["username"] in current_app.config["COE_LECTURERS"]
        ):
            user.roles.append("lecturer")
            user.roles.append("CoE-lecturer")
        elif (
            "COE_STAFFS" in current_app.config
            and userinfo["username"] in current_app.config["COE_STAFFS"]
        ):
            user.roles.append("staff")
            user.roles.append("CoE-staff")

        else:
            user.roles.append("staff")

        # if userinfo['username'].isdigit():
        #     project = models.Project.objects(
        #             student_ids=userinfo['username']).first()

        #     if project and user not in project.owners:
        #         project.owners.append(user)
        #         project.save()
    else:
        user.resources[client.engpsu.name] = userinfo
        user.last_login_date = datetime.datetime.now()

    user.save()

    login_user(user)

    oauth2token = models.OAuth2Token(
        name=client.engpsu.name,
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

    return redirect(url_for("dashboard.index"))


@module.route("/login/<name>")
def login_oauth(name):
    client = oauth2.oauth2_client
    scheme = request.environ.get("HTTP_X_FORWARDED_PROTO", "http")
    redirect_uri = url_for(
        "accounts.authorized_oauth", name=name, _external=True, _scheme=scheme
    )
    response = None
    if name == "google":
        response = client.google.authorize_redirect(redirect_uri)
    elif name == "facebook":
        response = client.facebook.authorize_redirect(redirect_uri)
    elif name == "line":
        response = client.line.authorize_redirect(redirect_uri)

    return response


@module.route("/auth/<name>")
def authorized_oauth(name):
    client = oauth2.oauth2_client
    remote = None
    try:
        if name == "google":
            remote = client.google
        elif name == "facebook":
            remote = client.facebook
        elif name == "line":
            remote = client.line

        token = remote.authorize_access_token()

    except Exception as e:
        print("autorize access error =>", e)
        return redirect(url_for("accounts.login"))

    return oauth2.handle_authorized_oauth2(remote, token)


@module.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("site.index"))


@module.route("/accounts/<user_id>")
def profile(user_id):
    user = models.User.objects.get(id=user_id)

    biography = ""
    if user.biography:
        biography = markdown.markdown(user.biography)
    return render_template("/accounts/index.html", user=user, biography=biography)


@module.route("/accounts")
@login_required
def index():

    biography = ""
    if current_user.biography:
        biography = markdown.markdown(current_user.biography)
    return render_template(
        "/accounts/index.html", user=current_user, biography=biography
    )


@module.route("/accounts/edit-profile", methods=["GET", "POST"])
@login_required
def edit_profile():
    form = forms.accounts.ProfileForm(
        obj=current_user,
    )
    if not form.validate_on_submit():
        return render_template("/accounts/edit-profile.html", form=form)

    user = current_user._get_current_object()
    form.populate_obj(user)

    if form.pic.data:
        if user.picture:
            user.picture.replace(
                form.pic.data,
                filename=form.pic.data.filename,
                content_type=form.pic.data.content_type,
            )
        else:
            user.picture.put(
                form.pic.data,
                filename=form.pic.data.filename,
                content_type=form.pic.data.content_type,
            )

    user.updated_date = datetime.datetime.now()
    user.save()

    return redirect(url_for("accounts.index"))


@module.route("/accounts/<user_id>/picture/<filename>", methods=["GET", "POST"])
def picture(user_id, filename):
    user = models.User.objects.get(id=user_id)

    if not user or not user.picture or user.picture.filename != filename:
        return abort(403)

    response = send_file(
        user.picture,
        download_name=user.picture.filename,
        mimetype=user.picture.content_type,
    )
    return response


@module.route("/user-roles")
@acl.roles_required('admin')
def user_roles():
    users = models.User.objects()
    if "admin" in current_user.roles:
        return render_template(
            "/accounts/user_roles.html",
            users=users,
        )
    return redirect(url_for("dashboard.daily_dashboard"))

@module.route("/user-roles/edit-roles", methods=["GET", "POST"])
@login_required
def edit_roles():
    if "admin" in current_user.roles:
        user_id=request.args.get("user_id")
        user = models.User.objects.get(id=user_id)
        form = forms.user_roles.UserRolesForm(obj=user)
        form.roles.choices = [
            ("admin", "Admin"),
            ("supervisor", "Supervisor"),
            ("user", "User"),
        ]
        
        if not form.validate_on_submit():
            return render_template(
                "/accounts/edit_roles.html",
                form=form,
            )

        form.populate_obj(user)
        user.roles = form.roles.data
        user.save()

        return redirect(url_for("accounts.user_roles"))
    return redirect(url_for("dashboard.daily_dashboard"))