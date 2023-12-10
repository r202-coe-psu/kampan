import mongoengine as me


class Supplier(me.Document):
    meta = {"collection": "suppliers"}

    name = me.StringField(required=True, max_length=256)
    description = me.StringField()
    address = me.StringField(required=True, max_length=256)
    # tax_id = me.IntField(required=True, max_length=256,  min_value = 1, default = 1)
    tax_id = me.StringField(required=True, max_length=256, default="")
    contact = me.StringField(max_length=256)
    email = me.StringField(required=True, max_length=256)
    phone = me.ListField(me.StringField())
    