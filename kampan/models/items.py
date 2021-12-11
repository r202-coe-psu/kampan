import mongoengine as me
import datetime


class ItemSize(me.EmbeddedDocument):
    width = me.FloatField()
    height = me.FloatField()
    deep = me.FloatField()


class Item(me.Document):
    meta = {"collection": "items"}

    name = me.StringField(required=True)
    description = me.StringField()
    size = me.EmbeddedDocumentField(ItemSize)
    weight = me.FloatField()
    categories = me.ListField(me.StringField(required=True))
    user = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now())
    updated_date = me.DateTimeField(required=True, default=datetime.datetime.now())
