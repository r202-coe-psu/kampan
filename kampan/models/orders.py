import mongoengine as me

class Itemregisteration(me.Document):
    meta = {"collection": "itemregister"}

    item_data = me.ReferenceField("Item",dbref=True)
    description = me.StringField()

    supplier = me.ReferenceField("Supplier",dbref=True)
    user = me.ReferenceField("User",dbref=True)
    quantity = me.FloatField(required=True)
    price = me.FloatField(required=True)
    status = me.ReferenceField("Status",dbref=True)
    date = me.StringField(required=True)
    expiration_date = me.StringField(required=True)
    location = me.StringField(required=True)

class Checkout(me.Document):
    meta = {"collection": "itemcheckout"}

    item_data = me.ReferenceField("Item",dbref=True)
    description = me.StringField()

    supplier = me.ReferenceField("Supplier",dbref=True)
    user = me.ReferenceField("User",dbref=True)
    quantity = me.FloatField(required=True)
    price = me.FloatField(required=True)
    status = me.ReferenceField("Status",dbref=True)
    date = me.StringField(required=True)