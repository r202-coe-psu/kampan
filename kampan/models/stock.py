import mongoengine as me

class Supplier(me.Document):
    meta = {"collection":"supplier"}

    orderfrom = me.StringField(required=True)
    description = me.StringField()

class User(me.Document):
    meta = {"collection":"users"}

    name = me.StringField(required=True)
    userid = me.Floatfield()

class Inventory(me.Document):
    meta = {"collection":"inventory"}

    itemdate = me.DocumentField(Item)
    itemregisteration = me.DocumentField(Itemregisteration)
    checkout = me.DocumentField(checkout)

class ItemStatus(me.Document):
    meta = {"collection":"status"}
    
    status = me.StringField(required=True)
    description = me.StringField