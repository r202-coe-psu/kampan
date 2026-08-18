import datetime
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


@pytest.fixture
def login_as(app):
    """เปิด test client แล้วผูก session ให้เป็นผู้ใช้ที่ระบุ"""

    def _login_as(client, user):
        with client.session_transaction() as sess:
            sess["_user_id"] = str(user.id)
            sess["_fresh"] = True
        return client

    return _login_as


@pytest.fixture
def create_car():
    def _create_car(organization, license_plate="กก 1111", status="active"):
        car = models.vehicles.Car(
            license_plate=license_plate,
            organization=organization,
            status=status,
        )
        car.save()
        return car

    return _create_car


@pytest.fixture
def create_car_application():
    def _create_car_application(
        organization,
        car,
        location="สนามบินหาดใหญ่",
        status="active",
        departure_datetime=None,
        travel_type="one way",
    ):
        application = models.vehicle_applications.CarApplication(
            organization=organization,
            car=car,
            location=location,
            status=status,
            travel_type=travel_type,
            using_type="general",
            request_reason="ไปราชการ",
            departure_datetime=departure_datetime or datetime.datetime(2026, 1, 15, 8, 0),
            return_datetime=departure_datetime or datetime.datetime(2026, 1, 15, 17, 0),
        )
        application.save()
        return application

    return _create_car_application


@pytest.fixture
def make_question():
    """สร้าง QuestionTemplate แบบสั้น ๆ สำหรับประกอบแบบประเมินในเทสต์"""

    def _make_question(question_type="score", question_text=None, choice_list=None, is_required=False):
        return models.QuestionTemplate(
            question_text=question_text or f"คำถาม {question_type}",
            question_type=question_type,
            choice_list=choice_list or [],
            is_required=is_required,
        )

    return _make_question


@pytest.fixture
def create_feedback_template():
    def _create_feedback_template(organization, cars, name="แบบประเมินรถ", questions=None, description=""):
        template = models.CarFeedbackTemplate(
            name=name,
            organization=organization,
            cars=list(cars),
            description=description,
            questions=list(questions or []),
        )
        template.save()
        return template

    return _create_feedback_template


@pytest.fixture
def create_feedback_response():
    def _create_feedback_response(template, car, answers=None, car_application=None, created_date=None):
        response = models.CarFeedbackResponse(
            feedback_template=template,
            organization=template.organization,
            car=car,
            car_application=car_application,
            answers=list(answers or []),
            created_date=created_date or datetime.datetime(2026, 2, 1, 10, 0),
        )
        response.save()
        return response

    return _create_feedback_response


@pytest.fixture
def make_answer():
    def _make_answer(question, score=None, text=None, boolean=None, choices=None):
        return models.Answer(
            question_id=question.question_id,
            answer_score=score,
            answer_text=text,
            answer_boolean=boolean,
            answer_choices=list(choices or []),
        )

    return _make_answer
