from flask import url_for
from email.policy import default
import mongoengine as me
import datetime


class ItemSize(me.EmbeddedDocument):
    width = me.FloatField()
    height = me.FloatField()
    deep = me.FloatField()


class Item(me.Document):
    meta = {"collection": "items"}

    name = me.StringField(required=True, max_length=255)
    description = me.StringField()
    weight = me.FloatField()
    size = me.EmbeddedDocumentField(ItemSize)
    categories = me.ListField(me.StringField(required=True))
    images = me.ImageField(thumbnail_size=(800, 600, False))

    user = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(required=True, default=datetime.datetime.now)


class ItemPosition(me.Document):
    meta = {"collection": "item_positions"}

    rack = me.StringField(required=True, max_length=255)
    row = me.StringField(max_length=255)
    locker = me.StringField(max_length=255)

    warehouse = me.ReferenceField("Warehouse", dbref=True)

    user = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(required=True, default=datetime.datetime.now)
