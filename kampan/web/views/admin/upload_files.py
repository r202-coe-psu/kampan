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

import pandas as pd
from io import BytesIO

module = Blueprint("upload_files", __name__, url_prefix="/upload_files")


@module.route("/")
@login_required
@acl.roles_required("admin")
def index():
    organization = current_user.user_setting.current_organization
    documents_query = models.Document.objects(status__ne="disable")

    return render_template(
        "procurement/upload_files/index.html",
        organization=organization,
        documents=documents_query,
    )


@module.route("/create", methods=["GET", "POST"], defaults={"document_id": None})
@module.route("/<document_id>/edit", methods=["GET", "POST"])
@login_required
@acl.roles_required("admin")
def upload_or_edit(document_id):
    document = None
    form = forms.upload_files.FileForm()
    organization = current_user.user_setting.current_organization

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

    # Handle multiple file uploads
    if not document_id and form.document_upload.data:
        documents = []
        for file in form.document_upload.data:
            document = models.Document()
            document.created_by = current_user
            document.updated_by = current_user
            document.status = "waiting"

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

            category = "unknown"
            if df is not None:
                cols = set(col.lower() for col in df.columns)
                if {
                    "mas_code",
                    "main_category",
                    "sub_category",
                    "name",
                    "item_description",
                    "amount",
                    "budget",
                    "actual_cost",
                }.issubset(cols):
                    category = "mas"
                elif {
                    "product_number",
                    "asset_code",
                    "name",
                    "category",
                    "start_date",
                    "end_date",
                    "amount",
                    "period",
                    "quantity",
                    "company",
                    "responsible_by",
                }.issubset(cols):
                    category = "ma"

            document.category = category

            # Save file
            file_stream.seek(0)
            document.file.put(
                file_stream,
                filename=file.filename,
                content_type=file.content_type,
            )
            document.save()
            documents.append(document)

        if documents:
            return redirect(url_for("admin.upload_files.index"))

    # Handle single file edit
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

        form.populate_obj(document)
        document.updated_by = current_user
        document.status = "waiting"

        if form.document_upload.data:
            for file in form.document_upload.data:
                file_stream = BytesIO(file.read())
                df = None

                # Only auto-detect category for new files
                if not document_id:
                    try:
                        df = pd.read_excel(file_stream, engine="openpyxl")
                    except Exception:
                        try:
                            file_stream.seek(0)
                            df = pd.read_excel(file_stream, engine="xlrd")
                        except Exception as e:
                            print(f"Error reading Excel file: {e}")
                            df = None

                # Auto-detect category only for new files
                if df is not None:
                    cols = set(col.lower() for col in df.columns)
                    if {
                        "mas_code",
                        "main_category",
                        "sub_category",
                        "name",
                        "item_description",
                        "amount",
                        "budget",
                        "actual_cost",
                    }.issubset(cols):
                        form.category.data = "mas"
                    elif {
                        "product_number",
                        "asset_code",
                        "name",
                        "category",
                        "start_date",
                        "end_date",
                        "amount",
                        "period",
                        "quantity",
                        "company",
                        "responsible_by",
                    }.issubset(cols):
                        form.category.data = "ma"

                file_stream.seek(0)
                if document.id:
                    document.file.replace(
                        file_stream,
                        filename=file.filename,
                        content_type=file.content_type,
                    )
                    document.status = "waiting"
                else:
                    document.file.put(
                        file_stream,
                        filename=file.filename,
                        content_type=file.content_type,
                    )
        document.updated_date = datetime.datetime.now()

    # Use form category or fallback to auto-detected
    document.category = form.category.data
    document.save()

    return redirect(url_for("admin.upload_files.index"))


@module.route("/<document_id>/delete", methods=["GET", "POST"])
@login_required
@acl.roles_required("admin")
def delete(document_id):
    document = models.Document.objects.get(id=document_id)
    if document:
        document.status = "disable"
        document.save()

    return redirect(url_for("admin.upload_files.index"))


@module.route("/<document_id>/download/<filename>")
@login_required
@acl.roles_required("admin")
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
@acl.roles_required("admin")
def processing(document_id):
    document = models.Document.objects.get(id=document_id)
    document.status = "waiting"
    document.save()

    category = document.category or "unknown"

    print(category)
    if category == "mas":
        mas = models.MAS.objects(
            status="active",
        )
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

    return redirect(url_for("admin.upload_files.index"))
