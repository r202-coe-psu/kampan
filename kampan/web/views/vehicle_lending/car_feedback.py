from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    abort,
    send_file,
)
from flask_login import login_required, current_user
import mongoengine as me
from bson import ObjectId
import datetime
import io
import qrcode
import json

from kampan.web import forms, acl
from kampan import models

module = Blueprint("car_feedback", __name__, url_prefix="/car_feedback")


@module.route("", methods=["GET"])
@acl.organization_roles_required("admin")
def index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    if not organization:
        return abort(404)

    cars = models.vehicles.Car.objects(organization=organization)

    templates = models.CarFeedbackTemplate.objects(car__in=cars)

    return render_template(
        "/vehicle_lending/car_feedback/index.html",
        organization=organization,
        templates=templates,
    )


@module.route("/create", methods=["GET", "POST"], defaults={"template_id": None})
@module.route("/<template_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def create_or_edit(template_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()

    cars = models.vehicles.Car.objects(organization=organization)

    template = None
    if template_id:
        template = models.CarFeedbackTemplate.objects(
            id=template_id, car__in=cars
        ).first()
        if not template:
            return abort(404)

    form = forms.car_feedback.CarFeedbackTemplateForm(obj=template)

    cars = models.vehicles.Car.objects(organization=organization, status="active")
    car_choices = [(str(c.id), c.license_plate) for c in cars]
    form.car.choices = car_choices

    if request.method == "POST":
        name = form.name.data
        car_id = form.car.data
        description = form.description.data

        car = models.vehicles.Car.objects(id=car_id, organization=organization).first()
        if not car:
            return abort(400, "Invalid car selection")

        questions_json = request.form.get("questions_data")
        if not questions_json:
            return abort(400, "Missed questions data")

        questions = json.loads(questions_json)

        question_templates = []
        for q in questions:
            qt = models.QuestionTemplate()
            if "question_id" in q and q["question_id"]:
                try:
                    qt.question_id = ObjectId(q["question_id"])
                except Exception:
                    pass
            qt.question_text = q.get("question_text")
            qt.question_type = q.get("question_type")
            qt.choice_list = q.get("choice_list", [])
            qt.is_required = q.get("is_required", False)
            question_templates.append(qt)

        if not template:
            template = models.CarFeedbackTemplate()

        template.name = name
        template.car = car
        template.description = description
        template.questions = question_templates
        template.save()

        return redirect(
            url_for(
                "vehicle_lending.car_feedback.index", organization_id=organization_id
            )
        )

    return render_template(
        "/vehicle_lending/car_feedback/create_or_edit.html",
        organization=organization,
        template=template,
        template_id=template_id,
        cars=cars,
        car_choices=car_choices,
        form=form,
    )


@module.route("/<template_id>/qrcode")
@acl.organization_roles_required("admin")
def qr_code(template_id):
    organization_id = request.args.get("organization_id")
    template = models.CarFeedbackTemplate.objects(id=template_id).first()
    if not template or not template.car:
        return abort(404)

    feedback_url = url_for(
        "vehicle_lending.cars.feedback",
        car_id=template.car.id,
        _external=True,
    )

    img = qrcode.make(feedback_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(
        buf,
        mimetype="image/png",
        download_name=f"qrcode_form_{template.car.license_plate}.png",
    )


@module.route("/<template_id>/view", methods=["GET"])
@acl.organization_roles_required("admin")
def view_responses(template_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()

    template = models.CarFeedbackTemplate.objects(id=template_id).first()
    if not template:
        return abort(404)

    responses = models.car_feedback.CarFeedbackResponse.objects(
        feedback_template=template
    )

    stats = {}
    for q in template.questions:
        stats[str(q.question_id)] = {
            "type": q.question_type,
            "text": q.question_text,
            "responses": 0,
            "data": {},
        }
        if q.question_type == "score":
            stats[str(q.question_id)]["data"] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
            stats[str(q.question_id)]["average"] = 0
            stats[str(q.question_id)]["sum"] = 0
        elif q.question_type == "boolean":
            stats[str(q.question_id)]["data"] = {"true": 0, "false": 0}
        elif q.question_type in ["single_choice", "multiple_choice"]:
            for c in q.choice_list:
                stats[str(q.question_id)]["data"][c] = 0
        elif q.question_type == "text":
            stats[str(q.question_id)]["texts"] = []

    for r in responses:
        for ans in r.answers:
            qid = str(ans.question_id)
            if qid in stats:
                stats[qid]["responses"] += 1
                if stats[qid]["type"] == "score" and ans.answer_score:
                    stats[qid]["data"][ans.answer_score] += 1
                    stats[qid]["sum"] += ans.answer_score
                elif stats[qid]["type"] == "boolean" and ans.answer_boolean is not None:
                    if ans.answer_boolean:
                        stats[qid]["data"]["true"] += 1
                    else:
                        stats[qid]["data"]["false"] += 1
                elif stats[qid]["type"] == "single_choice" and ans.answer_text:
                    if ans.answer_text in stats[qid]["data"]:
                        stats[qid]["data"][ans.answer_text] += 1
                    else:
                        stats[qid]["data"][ans.answer_text] = 1
                elif stats[qid]["type"] == "multiple_choice" and ans.answer_choices:
                    for c in ans.answer_choices:
                        if c in stats[qid]["data"]:
                            stats[qid]["data"][c] += 1
                        else:
                            stats[qid]["data"][c] = 1
                elif stats[qid]["type"] == "text" and ans.answer_text:
                    stats[qid]["texts"].append(ans.answer_text)

    for qid, stat in stats.items():
        if stat["type"] == "score" and stat["responses"] > 0:
            stat["average"] = stat["sum"] / stat["responses"]

    return render_template(
        "/vehicle_lending/car_feedback/view.html",
        organization=organization,
        template=template,
        responses=responses,
        stats=stats,
    )


@module.route("/<template_id>/delete")
@acl.organization_roles_required("admin")
def delete(template_id):
    organization_id = request.args.get("organization_id")
    template = models.CarFeedbackTemplate.objects(id=template_id).first()
    if template:
        template.delete()
    return redirect(
        url_for("vehicle_lending.car_feedback.index", organization_id=organization_id)
    )
