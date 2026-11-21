import mongoengine as me


class CarHoliday(me.Document):
    organization = me.ReferenceField("Organization", required=True)
    date = me.DateField(required=True)
    name = me.StringField()

    meta = {
        "collection": "car_holidays",
        "indexes": [{"fields": ["organization", "date"], "unique": True}],
    }
