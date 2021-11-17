import mongoengine as me

class Supplier(me.Document):
    meta = {"collection":"supplier"}

    orderfrom = me.StringField(required=True)
    description = me.StringField()

class Users(me.Document):
    meta = {"collection":"users"}

    name = me.StringField(required=True)
    userid = me.FloatField()

class Inventory(me.Document):
    meta = {"collection":"inventory"}

    itemdate = me.ReferenceField("Item", dbref=True)
    itemregisteration = me.ReferenceField("Itemregisteration", dbref=True)
    checkout = me.ReferenceField("checkout", dbref=True)

class ItemStatus(me.Document):
    meta = {"collection":"status"}
    
    status = me.StringField(required=True)
    description = me.StringField