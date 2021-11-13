import mongoengine as me

class Itemregisteration(me.Document):
    meta = {"collection": "itemregister"}

    ItemData = me.DocumentField(Item)
    Description = me.StringField()

    Supplier = me.DocumentField(Supplier)
    User = me.DocumentField(User)
    Quantity = me.FloatField(required=True)
    Price = me.FloatField(required=True)
    Status = me.DocumentField(Status)
    Date = me.StringField(required=True)

class Checkout(me.Document):
    meta = {"collection": "itemcheckout"}

    ItemData = me.DocumentField(Item)
    Description = me.StringField()

    Supplier = me.DocumentField(Supplier)
    User = me.DocumentField(User)
    Quantity = me.FloatField(required=True)
    Price = me.FloatField(required=True)
    Status = me.DocumentField(Status)
    Date = me.StringField(required=True)