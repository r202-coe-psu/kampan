from kampan import models
from mongoengine import Q
import datetime


def get_data_item_report(start_date, end_date, item, organization):
    pipeline = [
        # {"$match": {"$and": [{"$gte": ["create_date", start_date]}]}},
        {
            "$project": {
                "date_time": "$created_date",
                "owner": "ยกยอด",
                "supplier": "",
                "amount": "",
            },
        },
    ]
    item_snapshot = models.ItemSnapshot.objects(
        Q(created_date__gte=start_date)
        & Q(created_date__lt=end_date + datetime.timedelta(days=1))
        & Q(item=item)
        & Q(organization=organization)
    ).aggregate(pipeline)
