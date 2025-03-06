import sys
import mongoengine as me

# import pandas as pd
from kampan import models
import datetime


def init_ordinal_number():
    organizations = models.Organization.objects(status="active")
    for organization in organizations:
        orders = models.OrderItem.objects(
            status="approved", organization=organization
        ).order_by("created_date")
        ordinal_number = 1
        for order in orders:
            order.ordinal_number = f"{ordinal_number}"
            order.save()
            ordinal_number += 1


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # me.connect(db="kampandb", host=sys.argv[1])
        me.connect(db="kampandb", host="mongodb", port=27017)
    else:
        me.connect(db="kampandb")
    print("start")
    init_ordinal_number()
    print("end")
