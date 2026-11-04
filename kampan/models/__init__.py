from flask_mongoengine import MongoEngine

from .users import User
from .oauth2 import OAuth2Token
from .items import Item, ItemPosition, ItemSnapshot
from .suppliers import Supplier
from .inventories import Inventory
from .warehouses import Warehouse
from .organizations import Organization, Logo, OrganizationUserRole
from .email_templates import EmailTemplate
from .divisions import Division
from .approve_orders import ApprovedCheckoutItem
from .item_checkouts import CheckoutItem, BaseCheckoutItem
from .item_orders import OrderEmail, OrderItem
from .item_registers import RegistrationItem
from .lost_break_items import LostBreakItem
from .categories import Category
from .procurement import (
    Procurement,
    RenewalConflict,
    ConcurrentEditConflict,
    ProcurementItem,
    Installment,
    CATEGORY_CHOICES,
    ITEM_CATEGORY_CHOICES,
    ACCOUNT_CODE_CHOICES,
    REMINDER_KIND_CHOICES,
    REMINDER_OFFSET_CHOICES,
    DEFAULT_REMINDER_OFFSETS,
    PAYEMENT_STATUS_CHOICES,
    RENEWAL_STATUS_CHOICES,
)
from .reminder_logs import ReminderLog, REMINDER_LOG_KINDS, REMINDER_LOG_STATUSES
from .mas import MAS, Reservation
from .requisitions import Requisition, RequisitionItem, Committees
from .upload_files import Document
import kampan.models.vehicles as vehicles
from .vehicles import Car, Motorcycle, CarFeedback
import kampan.models.car_feedback as car_feedback
from .car_feedback import (
    Answer,
    CarFeedbackResponse,
    CarFeedbackTemplate,
    QuestionTemplate,
    QUESTION_TYPE,
)
import kampan.models.vehicle_applications as vehicle_applications
from .requisition_timeline import (
    RequisitionTimeline,
    RequisitionTimelineItem,
    Progress,
    PROGRESS_STATUS_CHOICES,
    RequisitionTimelineLogs,
    CompletedProgressDetail,
    FundAllocation,
    FundAllocationSource,
)
from .export_file import ExportFile

db = MongoEngine()


def init_db(app):
    db.init_app(app)


def init_mongoengine(settings):
    import mongoengine as me

    dbname = settings.get("MONGODB_DB")
    host = settings.get("MONGODB_HOST", "localhost")
    port = int(settings.get("MONGODB_PORT", "27017"))
    username = settings.get("MONGODB_USERNAME", "")
    password = settings.get("MONGODB_PASSWORD", "")

    me.connect(db=dbname, host=host, port=port, username=username, password=password)
