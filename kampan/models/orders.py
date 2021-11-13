import mongoengine as me

class Itemregisteration(me.Document):
    meta = {"collection": "itemregister"}

    ItemData = me.ReferenceField(Item)
    Description = me.StringField()

    Supplier = me.ReferenceField("Supplier",dbref=True)
    User = me.ReferenceField("User",dbref=True)
    Quantity = me.FloatField(required=True)
    Price = me.FloatField(required=True)
    Status = me.ReferenceField("Status",dbref=True)
    Date = me.StringField(required=True)
    expiration_date = me.StringField(required=True)
    location = me.StringField(required=True)

class Checkout(me.Document):
    meta = {"collection": "itemcheckout"}

    ItemData = me.ReferenceField(Item)
    Description = me.StringField()

    Supplier = me.ReferenceField(Supplier)
    User = me.ReferenceField(User)
    Quantity = me.FloatField(required=True)
    Price = me.FloatField(required=True)
    Status = me.ReferenceField(Status)
    Date = me.StringField(required=True)