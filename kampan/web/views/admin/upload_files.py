from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    send_file,
    request,
    Response,
)
from flask_login import login_required, current_user
import datetime

from ... import models, forms, acl, redis_rq
from .... import utils
from ....utils.upload_files import (
    MAS_COLUMNS,
    MA_COLUMNS,
    MAS_COLUMN_MAP,
    MA_COLUMN_MAP,
    generate_mas_template,
    generate_ma_template,
    validate_mas_file,
    validate_ma_file,
)

import pandas as pd
from io import BytesIO

module = Blueprint("upload_files", __name__, url_prefix="/upload_files")


@module.route("/")
@login_required
@acl.organization_roles_required("admin")
def index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    documents_query = models.Document.objects(status__ne="disable")

    return render_template(
        "procurement/upload_files/index.html",
        organization=organization,
        documents=documents_query,
    )


@module.route("/create", methods=["GET", "POST"], defaults={"document_id": None})
@module.route("/<document_id>/edit", methods=["GET", "POST"])
@login_required
@acl.organization_roles_required("admin")
def upload_or_edit(document_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()

    document = None
    if document_id:
        document = models.Document.objects(id=document_id).first()

    form = forms.upload_files.FileForm(obj=document)

    if not form.validate_on_submit():
        return render_template(
            "procurement/upload_files/upload_or_edit.html",
            form=form,
            document=document,
            organization=organization,
        )

    # ---- CREATE ----
    if not document_id:
        for file in form.document_upload.data:
            if not getattr(file, "filename", None):
                continue

            new_doc = models.Document()
            new_doc.created_by = current_user
            new_doc.updated_by = current_user
            new_doc.status = "waiting"
            new_doc.error_messages = []

            file_stream = BytesIO(file.read())
            try:
                df = pd.read_excel(file_stream, engine="openpyxl")
            except Exception:
                try:
                    file_stream.seek(0)
                    df = pd.read_excel(file_stream, engine="xlrd")
                except Exception as e:
                    print(f"Error reading Excel file: {e}")
                    df = None

            category = form.category.data or "unknown"
            if df is not None:
                cols = set(df.columns)
                cols_lower = set(col.lower() for col in df.columns)
                if set(MAS_COLUMN_MAP.values()).issubset(cols) or set(
                    MAS_COLUMNS
                ).issubset(cols_lower):
                    category = "mas"
                elif set(MA_COLUMN_MAP.values()).issubset(cols) or set(
                    MA_COLUMNS
                ).issubset(cols_lower):
                    category = "ma"

            new_doc.category = category

            file_stream.seek(0)
            new_doc.file.put(
                file_stream,
                filename=file.filename,
                content_type=file.content_type,
            )
            new_doc.save()

    # ---- EDIT ----
    else:
        form.populate_obj(document)
        document.updated_by = current_user
        document.status = "waiting"
        document.error_messages = []

        files = [
            f for f in (form.document_upload.data or []) if getattr(f, "filename", None)
        ]
        if files:
            file = files[0]
            file_stream = BytesIO(file.read())

            try:
                df = pd.read_excel(file_stream, engine="openpyxl")
            except Exception:
                try:
                    file_stream.seek(0)
                    df = pd.read_excel(file_stream, engine="xlrd")
                except Exception as e:
                    print(f"Error reading Excel file: {e}")
                    df = None

            if df is not None:
                cols = set(df.columns)
                cols_lower = set(col.lower() for col in df.columns)
                if set(MAS_COLUMN_MAP.values()).issubset(cols) or set(
                    MAS_COLUMNS
                ).issubset(cols_lower):
                    document.category = "mas"
                elif set(MA_COLUMN_MAP.values()).issubset(cols) or set(
                    MA_COLUMNS
                ).issubset(cols_lower):
                    document.category = "ma"
                else:
                    document.category = form.category.data or "unknown"
            else:
                document.category = form.category.data or "unknown"

            file_stream.seek(0)
            if document.file:
                document.file.replace(
                    file_stream,
                    filename=file.filename,
                    content_type=file.content_type,
                )
            else:
                document.file.put(
                    file_stream,
                    filename=file.filename,
                    content_type=file.content_type,
                )
        else:
            document.category = form.category.data or document.category

        document.updated_date = datetime.datetime.now()
        document.save()

    return redirect(
        url_for("admin.upload_files.index", organization_id=organization.id)
    )


@module.route("/template/mas")
@login_required
@acl.organization_roles_required("admin")
def download_mas_template():
    buf = generate_mas_template()
    return send_file(
        buf,
        as_attachment=True,
        download_name="mas_template.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@module.route("/template/ma")
@login_required
@acl.organization_roles_required("admin")
def download_ma_template():
    buf = generate_ma_template()
    return send_file(
        buf,
        as_attachment=True,
        download_name="ma_template.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@module.route("/<document_id>/delete", methods=["GET", "POST"])
@login_required
@acl.organization_roles_required("admin")
def delete(document_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    document = models.Document.objects.get(id=document_id)
    if document:
        document.status = "disable"
        document.save()

    return redirect(
        url_for("admin.upload_files.index", organization_id=organization.id)
    )


@module.route("/<document_id>/download/<filename>")
@login_required
@acl.organization_roles_required("admin")
def download(document_id, filename):
    response = Response()
    response.status_code = 404

    document = models.Document.objects(id=document_id).first()

    if document:
        response = send_file(
            document.file,
            download_name=document.file.filename,
            mimetype=document.file.content_type,
        )

    return response


@module.route("/<document_id>/process", methods=["GET"])
@login_required
@acl.organization_roles_required("admin")
def processing(document_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    document = models.Document.objects.get(id=document_id)

    category = document.category or "unknown"

    errors = []
    if category == "mas":
        errors = validate_mas_file(document)
    elif category == "ma":
        errors = validate_ma_file(document)

    if errors:
        document.status = "failed"
        document.error_messages = errors
        document.updated_date = datetime.datetime.now()
        document.save()
        return redirect(
            url_for("admin.upload_files.index", organization_id=organization.id)
        )

    document.status = "waiting"
    document.error_messages = []
    document.save()

    if category == "mas":
        mas = models.MAS.objects(status="active")
        job = redis_rq.redis_queue.queue.enqueue(
            utils.upload_files.save_mas_db,
            args=(document, mas, current_user.id),
            timeout=600,
            job_timeout=600,
        )
        print("=====> MAS creation job submitted", job.get_id())
    elif category == "ma":
        ma = models.Procurement.objects()
        job = redis_rq.redis_queue.queue.enqueue(
            utils.upload_files.save_ma_db,
            args=(document, ma, current_user.id),
            timeout=600,
            job_timeout=600,
        )
        print("=====> MA creation job submitted", job.get_id())

    return redirect(
        url_for("admin.upload_files.index", organization_id=organization.id)
    )
