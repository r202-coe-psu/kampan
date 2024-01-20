from flask import Blueprint, render_template
from ... import acl

module = Blueprint("site", __name__)


@module.route("/")
def index():
    return render_template("sites/index.html")
