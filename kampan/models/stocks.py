import mongoengine as me


class Supplier(me.Document):
    meta = {"collection": "supplier"}

    order_from = me.StringField(required=True)
    description = me.StringField()


class Inventory(me.Document):
    meta = {"collection": "inventory"}

    # itemdate = me.ReferenceField("Item", dbref=True)
    # itemregisteration = me.ReferenceField("Itemregisteration", dbref=True)
    # checkout = me.ReferenceField("checkout", dbref=True)


class ItemStatus(me.Document):
    meta = {"collection": "status"}

    status = me.StringField(required=True)
    description = me.StringField()
