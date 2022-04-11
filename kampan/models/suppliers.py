import mongoengine as me


class Supplier(me.Document):
    meta = {"collection": "suppliers"}

    name = me.StringField(required=True, max_length=256)
    description = me.StringField()
    address = me.StringField()
    tax_id = me.IntField()
    contact = me.StringField()
    email = me.StringField()
    phone = me.ListField(me.StringField())
