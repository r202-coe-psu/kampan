from typing import Optional
from kampan.models.item_registers import RegistrationItem
from kampan.models.items import Item
from kampan.models.warehouses import Warehouse
from kampan.web.forms.inventories import InventoryForm
from bson import ObjectId


class RegisterItemRepository:
    @staticmethod
    def get_inventory_form(
        item_register_id: str,
        organization_id: str,
    ):
        item_register = RegistrationItem.objects.get(id=item_register_id)
        item_in_bill = item_register.get_item_in_bills()
        form = InventoryForm()
        form.item.choices = [
            (str(item.id), item.name)
            for item in Item.objects(status="active", organization=organization_id)
            if item not in item_in_bill
        ]
        form.warehouse.choices = [
            (str(warehouse.id), warehouse.name)
            for warehouse in Warehouse.objects(
                status="active", organization=organization_id
            )
        ]
        return form
