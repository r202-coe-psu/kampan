from flask import Blueprint, render_template, redirect, url_for
import datetime
from ... import acl

module = Blueprint("vehicle_lending", __name__, url_prefix="/vehicle_lending")
