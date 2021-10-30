from flask import Blueprint

module = Blueprint("site", __name__)


@module.route("/")
def index():
    return {"message": "Hello, Flask!", "success": True}
