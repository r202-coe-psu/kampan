"""เติมฟิลด์ organization ให้เอกสาร car feedback ที่บันทึกไว้ก่อนจะมีฟิลด์นี้

CarFeedbackTemplate/CarFeedbackResponse เดิมผูกหน่วยงานผ่าน cars อย่างเดียว
สคริปต์นี้ resolve หน่วยงานจากรถของเอกสารนั้น แล้วเขียนกลับลงฟิลด์ organization
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from flask import Flask

from kampan import models


def get_organization_from_cars(cars):
    for car in cars or []:
        organization = getattr(car, "organization", None)
        if organization:
            return organization

    return None


def backfill_templates():
    updated = 0
    skipped = []
    for template in models.CarFeedbackTemplate.objects(organization__exists=False):
        organization = get_organization_from_cars(template.cars)
        if not organization:
            skipped.append(str(template.id))
            continue

        template.organization = organization
        template.save()
        updated += 1

    return updated, skipped


def backfill_responses():
    updated = 0
    skipped = []
    for response in models.CarFeedbackResponse.objects(organization__exists=False):
        organization = get_organization_from_cars([response.car])
        if not organization:
            skipped.append(str(response.id))
            continue

        response.organization = organization
        response.save()
        updated += 1

    return updated, skipped


def migrate():
    template_count, template_skipped = backfill_templates()
    print(f"Updated {template_count} car feedback templates.")
    if template_skipped:
        print(f"Skipped templates without a resolvable organization: {template_skipped}")

    response_count, response_skipped = backfill_responses()
    print(f"Updated {response_count} car feedback responses.")
    if response_skipped:
        print(f"Skipped responses without a resolvable organization: {response_skipped}")


if __name__ == "__main__":
    app = Flask(__name__)
    app.config.from_pyfile(os.path.join(os.path.dirname(__file__), "..", "kampan-development.cfg"))
    models.init_mongoengine(app.config)

    migrate()
