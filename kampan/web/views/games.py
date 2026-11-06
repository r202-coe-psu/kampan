from flask import Blueprint, render_template

module = Blueprint("games", __name__, url_prefix="/games")


@module.route("")
def index():
    return render_template("games/index.html")
