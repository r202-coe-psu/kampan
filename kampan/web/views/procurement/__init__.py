from flask import Blueprint, render_template, redirect, url_for
import datetime
from ... import acl

module = Blueprint("procurement", __name__, url_prefix="/procurement")
