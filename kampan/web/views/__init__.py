import datetime
import importlib
import logging
import pathlib

from flask import request, url_for

from kampan.utils import template_filters

logger = logging.getLogger(__name__)


def add_date_url(url):
    now = datetime.datetime.now()
    return f'{url}?date={now.strftime("%Y%m%d")}'


# หน้าแรกของแต่ละโมดูล ใช้เวลาสลับหน่วยงานเพื่อพากลับไปตั้งต้นของโมดูลนั้น
MODULE_HOME_ENDPOINTS = {
    "procurement": "procurement.requisitions.renewal_requested",
    "vehicle_lending": "vehicle_lending.car_applications.calendar",
    "admin": "admin.index",
}
INVENTORY_HOME_ENDPOINT = "item_orders.index"
MOTORCYCLE_HOME_ENDPOINT = "vehicle_lending.motorcycle_applications.calendar"
NON_MODULE_BLUEPRINTS = {"site", "accounts", "organizations", "notifications"}


def switch_organization_next_url(organization):
    """หา URL หน้าแรกของโมดูลที่ผู้ใช้อยู่ เพื่อ redirect หลังสลับหน่วยงาน

    ไม่พากลับหน้าเดิม เพราะข้อมูลบนหน้านั้นมักผูกกับหน่วยงานเดิม (เช่นหน้ารายละเอียด)
    """

    if not request.endpoint or request.endpoint == "static":
        return None

    module_name = request.endpoint.split(".")[0]
    endpoint = MODULE_HOME_ENDPOINTS.get(module_name)

    if module_name == "vehicle_lending" and "motorcycle" in request.endpoint:
        endpoint = MOTORCYCLE_HOME_ENDPOINT

    if not endpoint:
        if module_name in NON_MODULE_BLUEPRINTS:
            # หน้าเลือกระบบ/บัญชี ไม่ได้อยู่ในโมดูลใด ให้ view จัดการ fallback เอง
            return None
        # โมดูลคลังพัสดุอยู่ที่ blueprint ระดับบนสุดหลายตัว จึงใช้หน้าแรกร่วมกัน
        endpoint = INVENTORY_HOME_ENDPOINT

    try:
        if endpoint == "admin.index":
            return url_for(endpoint)
        return url_for(endpoint, organization_id=str(organization.id))
    except Exception:
        return None


def get_subblueprints(directory):
    blueprints = []

    package = directory.parts[len(pathlib.Path.cwd().parts) :]
    parent_module = None
    try:
        parrent_view = directory.with_name("__init__.py")
        pymod_file = f"{'.'.join(package)}"
        pymod = importlib.import_module(pymod_file)

        if "module" in dir(pymod):
            parent_module = pymod.module
            blueprints.append(parent_module)
    except Exception as e:
        logger.exception(e)
        return blueprints

    subblueprints = []
    for module in directory.iterdir():

        if "__" == module.name[:2]:
            continue

        if module.match("*.py"):
            try:
                pymod_file = f"{'.'.join(package)}.{module.stem}"
                pymod = importlib.import_module(pymod_file)

                if "module" in dir(pymod):
                    subblueprints.append(pymod.module)
            except Exception as e:
                logger.exception(e)

        elif module.is_dir():
            subblueprints.extend(get_subblueprints(module))

    for module in subblueprints:
        if parent_module:
            parent_module.register_blueprint(module)
        else:
            blueprints.append(module)

    return blueprints


def register_blueprint(app):
    app.add_template_filter(template_filters.static_url)
    app.add_template_filter(template_filters.format_date)
    app.add_template_filter(template_filters.format_number)
    app.add_template_filter(template_filters.format_amount)
    app.add_template_filter(template_filters.format_thai_datetime_short_month)
    app.add_template_filter(template_filters.format_thai_date)
    app.add_template_filter(add_date_url)
    app.add_template_global(switch_organization_next_url)
    parent = pathlib.Path(__file__).parent
    blueprints = get_subblueprints(parent)

    for blueprint in blueprints:
        app.register_blueprint(blueprint)
