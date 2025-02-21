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
    meta = {"collection": "cars"}


class Motorcycle(BaseVehicle, me.Document):
    last_mileage = me.IntField(min_value=0, required=True, default=0)

    meta = {"collection": "motorcycles"}
