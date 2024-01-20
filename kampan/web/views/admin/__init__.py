from flask import Blueprint, render_template, redirect, url_for
import datetime


module = Blueprint("admin", __name__, url_prefix="/admin")
