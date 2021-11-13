from flask import g, config, session, redirect, url_for
from flask_login import current_user, login_user
from authlib.integrations.flask_client import OAuth
import loginpass

from . import models
import mongoengine as me

import datetime

def fetch_token(name):
    token = models.OAuth2Token.objects(name=name,
            user=current_user._get_current_object()).first()
    return token.to_dict()

def update_token(name, token):
    item = models.OAuth2Token(name=name, user=current_user._get_current_object()).first()
    item.token_type = token.get('token_type', 'Bearer')
    item.access_token = token.get('access_token')
    item.refresh_token = token.get('refresh_token')
    item.expires = datetime.datetime.utcfromtimestamp(token.get('expires_at'))
    
    item.save()
    return item


oauth2_client = OAuth()

def handle_authorize(remote, token, user_info):

    if not user_info:
        return redirect(url_for('accounts.login'))

    user = models.User.objects(
            me.Q(username=user_info.get('name')) | \
            me.Q(email=user_info.get('email'))
            ).first()
    if not user:
        user = models.User(
            username=user_info.get('name'),
            email=user_info.get('email'),
            first_name=user_info.get('given_name', ''),
            last_name=user_info.get('family_name', ''),
            status='active')
        user.resources[remote.name] = user_info
        email = user_info.get('email')
        if email[:email.find('@')].isdigit():
            user.roles.append('student')
        user.save()

    login_user(user)

    if token:
        oauth2token = models.OAuth2Token(
                name=remote.name,
                user=user,
                access_token=token.get('access_token'),
                token_type=token.get('token_type'),
                refresh_token=token.get('refresh_token', None),
                expires=datetime.datetime.utcfromtimestamp(
                token.get('expires_in'))
                )
        oauth2token.save()

    return redirect(url_for('dashboard.index'))


# def create_flask_blueprint(backend, oauth, handle_authorize):
#     from flask import Blueprint, request, url_for, current_app, session
#     from authlib.flask.client import RemoteApp
#     from authlib.common.security import generate_token
#     from loginpass._core import register_to

#     remote = register_to(backend, oauth, RemoteApp)
#     nonce_key = '_{}:nonce'.format(backend.OAUTH_NAME)
#     bp = Blueprint('loginpass_' + backend.OAUTH_NAME, __name__)

#     @bp.route('/auth')
#     def auth():
#         id_token = request.args.get('id_token')
#         if request.args.get('code'):
#             token = remote.authorize_access_token(verify=False)
#             if id_token:
#                 token['id_token'] = id_token
#         elif id_token:
#             token = {'id_token': id_token}
#         elif request.args.get('oauth_verifier'):
#             # OAuth 1
#             token = remote.authorize_access_token(verify=False)
#         else:
#             # handle failed
#             return handle_authorize(remote, None, None)
#         if 'id_token' in token:
#             nonce = session[nonce_key]
#             user_info = remote.parse_openid(token, nonce)
#         else:
#             user_info = remote.profile(token=token)
#         return handle_authorize(remote, token, user_info)

#     @bp.route('/login')
#     def login():
#         redirect_uri = url_for('.auth', _external=True)
#         conf_key = '{}_AUTHORIZE_PARAMS'.format(backend.OAUTH_NAME.upper())
#         params = current_app.config.get(conf_key, {})
#         if 'oidc' in backend.OAUTH_TYPE:
#             nonce = generate_token(20)
#             session[nonce_key] = nonce
#             params['nonce'] = nonce
#         return remote.authorize_redirect(redirect_uri, **params)

#     return bp


def init_oauth(app):
    oauth2_client.init_app(app,
                           fetch_token=fetch_token,
                           update_token=update_token)
    
    # oauth2_client.register('principal')
    oauth2_client.register('engpsu')
    # oauth2_client.register('google')
    backends = [loginpass.Google]

    loginpass_bp = loginpass.create_flask_blueprint(
            backends,
            oauth2_client,
            handle_authorize)
    app.register_blueprint(loginpass_bp)
