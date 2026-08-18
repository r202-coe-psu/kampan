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


def switch_organization_next_url(organization):

    if not request.endpoint or request.endpoint == "static":
        return None

    values = dict(request.view_args or {})
    values.update(request.args.to_dict())
    values["organization_id"] = str(organization.id)

    try:
        return url_for(request.endpoint, **values)
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
