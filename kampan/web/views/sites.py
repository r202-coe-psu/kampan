from flask import Blueprint, render_template

module = Blueprint("site", __name__)


@module.route("/")
def index():
    return render_template('sites/index.html')
