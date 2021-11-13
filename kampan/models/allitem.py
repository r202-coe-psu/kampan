import mongoengine as me

class Item(me.Document):
    meta = {"collection" : "items"}
    
    name = me.StringField(required=True)
    description = me.StringField()
    itemid = me.StringField()
    size = me.EmbeddedDocumentField(ItemSize)
    weight = me.Floatfield()
    Category = me.StringField(required=True)
    Location = me.StringField(required=True)
    ExpirationDate = me.StringField()

class ItemSize(me.EmbeddedDocumentField):
    width = me.Floatfield()
    Height = me.Floatfield()
    Deep = me.Floatfield()