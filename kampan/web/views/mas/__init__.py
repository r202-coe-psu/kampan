from flask import Blueprint

from . import projects

mas = Blueprint("mas", __name__, url_prefix="/mas")

mas.register_blueprint(projects.projects, url_prefix="/projects")
