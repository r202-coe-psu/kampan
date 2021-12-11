import mongoengine as me


class Supplier(me.Document):
    meta = {"collection": "suppliers"}

    name = me.StringField(required=True)
    address = me.StringField()
    description = me.StringField()
    tax_id = me.IntField()
    contact = me.StringField()
    email = me.StringField()


class Inventory(me.Document):
    meta = {"collection": "inventories"}

    name = me.StringField(required=True)
    # itemdate = me.ReferenceField("Item", dbref=True)
    # itemregisteration = me.ReferenceField("Itemregisteration", dbref=True)
    # checkout = me.ReferenceField("checkout", dbref=True)
