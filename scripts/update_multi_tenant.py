import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import kampan
from kampan import models

import mongoengine as me

# Initialize MongoEngine connection
from flask import Flask

app = Flask(__name__)
app.config.from_pyfile(os.path.join(os.path.dirname(__file__), "..", "kampan-development.cfg"))

models.init_mongoengine(app.config)


def migrate():
    org_id = "6661c367df36be9c312058ae"
    try:
        org = models.Organization.objects.get(id=org_id)
        print(f"Found organization: {org.name}")
    except Exception as e:
        print(f"Error finding organization {org_id}: {e}")
        return

    print("Updating Procurements...")
    procurements = models.Procurement.objects(organization__exists=False)
    count = 0
    for p in procurements:
        p.organization = org
        p.save()
        count += 1
    print(f"Updated {count} procurements.")

    print("Updating Requisitions...")
    requisitions = models.Requisition.objects(organization__exists=False)
    count = 0
    for r in requisitions:
        r.organization = org
        r.save()
        count += 1
    print(f"Updated {count} requisitions.")

    print("Updating Requisition Timelines...")
    timelines = models.RequisitionTimeline.objects(organization__exists=False)
    count = 0
    for t in timelines:
        t.organization = org
        t.save()
        count += 1
    print(f"Updated {count} timelines.")

    print("Updating Requisition Timeline Items...")
    items = models.RequisitionTimelineItem.objects(organization__exists=False)
    count = 0
    for i in items:
        i.organization = org
        i.save()
        count += 1
    print(f"Updated {count} timeline items.")

    print("Updating MAS...")
    mas_list = models.MAS.objects(organization__exists=False)
    count = 0
    for m in mas_list:
        m.organization = org
        m.save()
        count += 1
    print(f"Updated {count} MAS.")

    print("Updating Reservations...")
    reservations = models.Reservation.objects(organization__exists=False)
    count = 0
    for r in reservations:
        r.organization = org
        r.save()
        count += 1

    print(f"Updated {count} reservations.")

    print("Updating Documents...")
    documents = models.Document.objects(organization__exists=False)
    count = 0
    for d in documents:
        d.organization = org
        d.save()
        count += 1
    print(f"Updated {count} documents.")

    print("Migration complete.")


if __name__ == "__main__":
    migrate()
