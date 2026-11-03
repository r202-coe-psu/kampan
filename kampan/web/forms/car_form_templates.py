from flask_wtf import FlaskForm
from wtforms import fields, validators, widgets

from kampan import utils


def _field_type_and_choices(field_def):
    source = field_def.get("source", "catalog")
    template_choices = tuple(field_def.get("choices") or ())
    if source == "catalog":
        catalog_field = utils.car_form_catalog.CATALOG[field_def["key"]]
        return catalog_field.field_type, template_choices or catalog_field.choices
    return field_def.get("field_type"), template_choices


def _default_label(field_def):
    if field_def.get("label"):
        return field_def["label"]
    if field_def.get("source", "catalog") == "catalog":
        return utils.car_form_catalog.CATALOG[field_def["key"]].default_label
    return field_def["key"]


def _build_field(field_def):
    field_type, choices = _field_type_and_choices(field_def)
    required = field_def.get("is_required", False)
    label = _default_label(field_def)
    message = f"กรุณากรอก {label}"

    if field_type in ("number",):
        gate = validators.InputRequired(message=message)
    else:
        gate = validators.DataRequired(message=message)
    check = [gate] if required else [validators.Optional()]

    if field_type == "radio":
        options = [(c, c) for c in choices]
        if not required:
            options.insert(0, ("", ""))
        return fields.SelectField(label, validators=check, choices=options)
    if field_type == "checkbox":
        return fields.SelectMultipleField(
            label,
            validators=check,
            choices=[(c, c) for c in choices],
            widget=widgets.ListWidget(prefix_label=False),
            option_widget=widgets.CheckboxInput(),
        )
    if field_type == "number":
        number_field = (
            fields.IntegerField
            if field_def.get("source", "catalog") == "catalog"
            else fields.FloatField
        )
        return number_field(label, validators=check)
    if field_type == "date":
        return fields.DateField(label, validators=check)
    if field_type == "textarea":
        return fields.TextAreaField(label, validators=check)
    return fields.StringField(label, validators=check)


def _details_key(field_def):
    if field_def.get("source", "catalog") == "catalog":
        return field_def["key"]
    return f"custom_{field_def['key']}"


def build_details_form(field_defs):
    keys = [_details_key(f) for f in field_defs]
    attrs = {key: _build_field(f) for key, f in zip(keys, field_defs)}

    def details(self):
        values = {}
        for key in keys:
            data = self[key].data
            values[key] = data.isoformat() if hasattr(data, "isoformat") else data
        return values

    attrs["details"] = details
    return type("DetailsForm", (FlaskForm,), attrs)
