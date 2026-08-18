import os
import pytest
import mongoengine as me
import mongomock
from flask import Flask

from kampan import models
from kampan.web import acl, oauth2, redis_rq, views


@pytest.fixture(scope="session")
def app():
    template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../kampan/web/templates"))
    static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../kampan/web/static"))

    flask_app = Flask("kampan.web", template_folder=template_dir, static_folder=static_dir)
    flask_app.config["SECRET_KEY"] = "test-secret-key"
    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    flask_app.config["MONGODB_SETTINGS"] = {
        "db": "kampan_test_db",
        "mongo_client_class": mongomock.MongoClient,
    }

    # Initialize extensions
    models.init_db(flask_app)
    acl.init_acl(flask_app)
    views.register_blueprint(flask_app)

    return flask_app


@pytest.fixture(autouse=True)
def clean_db():
    """Clean all collections before each test."""
    yield
    try:
        db = me.connection.get_db()
        for collection in db.list_collection_names():
            if not collection.startswith("system."):
                db.drop_collection(collection)
    except Exception:
        pass


@pytest.fixture
def create_org():
    def _create_org(name="Test Org", status="active"):
        org = models.Organization(name=name, status=status)
        org.save()
        return org
    return _create_org


@pytest.fixture
def create_user():
    def _create_user(first_name="Test", last_name="User", roles=None):
        user = models.User(
            first_name=first_name,
            last_name=last_name,
            email=f"{first_name.lower()}@test.com",
            username=f"{first_name.lower()}_{last_name.lower()}",
            roles=roles or [],
        )
        user.save()
        return user
    return _create_user


@pytest.fixture
def assign_user_to_org():
    def _assign(user, org, roles=None, status="active", added_by=None):
        admin_ref = added_by or user
        org_user_role = models.OrganizationUserRole(
            user=user,
            organization=org,
            roles=roles or ["staff"],
            status=status,
            added_by=admin_ref,
            last_modifier=admin_ref,
        )
        org_user_role.save()
        return org_user_role
    return _assign
