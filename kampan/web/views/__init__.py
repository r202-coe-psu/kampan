import datetime
import pathlib
import importlib

def add_date_url(url):
    now = datetime.datetime.now()
    return f'{url}?date={now.strftime("%Y%m%d")}'

def get_subblueprints(directory):
    blueprints = []
   
    package = directory.parts[len(pathlib.Path.cwd().parts):]
    parent_module = None
    try:
        parrent_view = directory.with_name('__init__.py')
        pymod_file = f"{'.'.join(package)}"
        pymod = importlib.import_module(pymod_file)

        if 'module' in dir(pymod):
            parent_module = pymod.module
            blueprints.append(parent_module)
    except Exception as e:
        print(e)
        return blueprints

    subblueprints = []
    for module in directory.iterdir():

        if '__' == module.name[: 2]:
            continue

        if module.match('*.py'):
            pymod_file = f"{'.'.join(package)}.{module.stem}"
            pymod = importlib.import_module(pymod_file)

            if 'module' in dir(pymod):
                subblueprints.append(pymod.module)

        elif module.is_dir():
            subblueprints.extend(get_subblueprints(module))

    for module in subblueprints:
        if parent_module:
            parent_module.register_blueprint(module)
        else:
            blueprints.append(module)

    return blueprints


def register_blueprint(app):
    app.add_template_filter(add_date_url)
    parent = pathlib.Path(__file__).parent
    blueprints = get_subblueprints(parent)

    for blueprint in blueprints:
        app.register_blueprint(blueprint)
