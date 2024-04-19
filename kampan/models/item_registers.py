from email.policy import default
import mongoengine as me
import datetime
from kampan import models


class RegistrationItem(me.Document):
    meta = {"collection": "registration_items"}

    bill = me.FileField(collection_name="bill_registration")
    status = me.StringField(default="active")
    receipt_id = me.StringField(required=True, max_length=255)
    description = me.StringField()

    supplier = me.ReferenceField("Supplier", dbref=True)
    created_by = me.ReferenceField("User", dbref=True)
    organization = me.ReferenceField("Organization", dbref=True)

    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)

    def get_item_in_bill(self):
        inventories = models.Inventory.objects(
            registration=self, status__ne="disactive"
        )
        if inventories:
            return [inventory.item.id for inventory in inventories]

    def get_quantity_of_item(self):
        quantiy_item = models.Inventory.objects(
            registration=self, status__ne="disactive"
        ).count()
        return quantiy_item
