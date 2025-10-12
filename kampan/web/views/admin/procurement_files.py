from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    send_file,
    abort,
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from kampan.web import forms, acl
from kampan.models.upload_history import UploadHistory
from kampan.utils.file_storage import save_file, get_file, delete_file
from kampan.utils.mas import upload_mas_excel, download_mas_template
from kampan.utils.procurements import (
    upload_procurement_excel,
    download_procurement_template,
)
import datetime

module = Blueprint("procurement_files", __name__, url_prefix="/procurement_files")


@module.route("/")
@login_required
@acl.roles_required("admin")
def index():
    organization = current_user.user_setting.current_organization
    upload_history = UploadHistory.objects.order_by("-upload_date")
    return render_template(
        "procurement/procurement_files/index.html",
        upload_history=upload_history,
        organization=organization,
    )


@module.route("/upload", methods=["GET", "POST"])
@login_required
def upload_or_edit():
    form = forms.upload.UploadExcelForm()

    if form.validate_on_submit():
        try:
            file = form.excel_file.data
            file_type = form.file_type.data

            file_bytes = file.read()
            filename = secure_filename(file.filename)

            # Save to GridFS
            file_id = save_file(
                file_bytes,
                filename=filename,
                content_type=file.content_type,
            )

            # Create upload history
            UploadHistory(
                file_name=filename,
                file_type=file_type,
                file_id=file_id,
                uploaded_by=current_user,
                upload_date=datetime.datetime.now(),
            ).save()

            # Process data based on type
            if file_type == "mas":
                upload_mas_excel(
                    file_bytes=file_bytes,
                    user_id=current_user.id,
                    filename=filename,
                    file_id=file_id,
                )
            elif file_type == "procurement":
                upload_procurement_excel(
                    file_bytes=file_bytes,
                    user_id=current_user.id,
                    filename=filename,
                    file_id=file_id,
                )

            return redirect(url_for("admin.procurement_files.index"))

        except Exception:
            pass

    return render_template(
        "procurement/procurement_files/upload.html",
        form=form,
        organization=current_user.user_setting.current_organization,
    )


@module.route("/download/<file_id>")
@login_required
def download(file_id):
    file_data = get_file(file_id)
    if not file_data:
        abort(404)

    return send_file(
        file_data["file_stream"],
        download_name=file_data["filename"],
        as_attachment=True,
        mimetype=file_data["content_type"],
    )


@module.route("/delete/<file_id>", methods=["POST"])
@login_required
def delete(file_id):
    upload_history = UploadHistory.objects(file_id=file_id).first()
    if not upload_history:
        abort(404)

    delete_file(file_id)
    upload_history.delete()
    return redirect(url_for("admin.procurement_files.index"))


@module.route("/<file_type>/download_template")
@login_required
def download_template(file_type):
    if file_type == "mas":
        return download_mas_template()
    elif file_type == "procurement":
        return download_procurement_template()
    else:
        abort(404)
