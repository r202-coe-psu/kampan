import mongoengine as me
import datetime


VEHICLE_STATUS = [
    ("active", "สามารถใช้งานได้"),
    ("disactive", "ไม่สามารถใช้งานได้"),
]


class BaseVehicle:
    image = me.ImageField()

    license_plate = me.StringField(default="", max_length=256, required=True)
    description = me.StringField(default="")

    status = me.StringField(default="active", choices=VEHICLE_STATUS)
    creator = me.ReferenceField("User", dbref=True)
    updater = me.ReferenceField("User", dbref=True)

    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )
    organization = me.ReferenceField("Organization", dbref=True, required=True)


class Car(BaseVehicle, me.Document):
    last_mileage = me.IntField(min_value=0, required=True, default=0)
    meta = {"collection": "cars"}


class CarFeedback(me.Document):
    car = me.ReferenceField("Car", dbref=True, required=True)
    start_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    end_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    driver_politeness_score = me.IntField(min_value=1, max_value=5, required=True)
    driving_safety_score = me.IntField(min_value=1, max_value=5, required=True)
    car_cleanliness_score = me.IntField(min_value=1, max_value=5, required=True)
    overall = me.IntField(min_value=1, max_value=5, required=True)
    comment = me.StringField(default="", max_length=512)

    meta = {"collection": "car_feedbacks"}


class Motorcycle(BaseVehicle, me.Document):
    last_mileage = me.IntField(min_value=0, required=True, default=0)

    meta = {"collection": "motorcycles"}
