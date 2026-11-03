import datetime

import pytest
from jinja2.exceptions import SecurityError

from kampan import models
from kampan.utils import car_form_paper


@pytest.fixture
def make_application(app, create_org, create_user, assign_user_to_org, create_car):
    def _make(paper_html, location="สนามบินหาดใหญ่", details=None, approvers=None):
        org = create_org(name="กองกายภาพ")
        requester = create_user("Somchai", "Jaidee")
        assign_user_to_org(requester, org, roles=["staff"])
        car = create_car(org, license_plate="กข-1234")

        step_approvals = []
        for step_key, approver, decided_at in approvers or []:
            step_approvals.append(
                models.vehicle_applications.StepApproval(
                    step_key=step_key,
                    decision="approved",
                    decided_by=approver,
                    decided_at=decided_at,
                )
            )

        application = models.vehicle_applications.CarApplication(
            organization=org,
            creator=requester,
            car=car,
            location=location,
            request_reason="ไปราชการ",
            departure_datetime=datetime.datetime(2026, 11, 3, 8, 30),
            return_datetime=datetime.datetime(2026, 11, 3, 17, 0),
            details=details or {},
            step_approvals=step_approvals,
            template_snapshot={"paper_html": paper_html},
        )
        application.save()
        return application

    return _make


def test_paper_shows_requester_location_thai_departure_date_details_and_step_approver(
    make_application, create_user
):
    head = create_user("Prasert", "Meesuk")
    application = make_application(
        paper_html=(
            "ผู้ขอ={{ app.requester_name }};"
            "สถานที่={{ app.location }};"
            "ไป={{ app.departure.day }} {{ app.departure.month_th }} {{ app.departure.year_be }};"
            "ผู้โดยสาร={{ details.passengers_note }};"
            "หัวหน้า={{ approvals.head.name }}"
        ),
        details={"passengers_note": "นักศึกษา 3 คน"},
        approvers=[("head", head, datetime.datetime(2026, 11, 2, 10, 0))],
    )

    html = car_form_paper.render_paper(application)

    assert html == (
        "ผู้ขอ=Somchai Jaidee;"
        "สถานที่=สนามบินหาดใหญ่;"
        "ไป=3 พฤศจิกายน 2569;"
        "ผู้โดยสาร=นักศึกษา 3 คน;"
        "หัวหน้า=Prasert Meesuk"
    )


def test_paper_values_are_html_escaped(make_application):
    application = make_application(
        paper_html="<p>{{ app.location }}</p>",
        location="<script>alert(1)</script>",
    )

    html = car_form_paper.render_paper(application)

    assert html == "<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>"


def test_paper_html_reaching_python_internals_raises_security_error(make_application):
    application = make_application(paper_html="{{ ''.__class__.__mro__[1].__subclasses__() }}")

    with pytest.raises(SecurityError):
        car_form_paper.render_paper(application)


def test_paper_missing_details_key_renders_empty_not_an_error(make_application):
    application = make_application(
        paper_html="[{{ details.not_filled_in }}][{{ approvals.head.name }}]",
    )

    html = car_form_paper.render_paper(application)

    assert html == "[][]"
