import datetime
import mongoengine as me


class UploadHistory(me.Document):
    meta = {"collection": "upload_history"}

    # File information
    file_name = me.StringField(max_length=255, required=True)
    file_type = me.StringField(choices=["mas", "procurement"], required=True)
    file_id = me.ObjectIdField(required=True)

    # Upload metadata
    uploaded_by = me.ReferenceField("User", dbref=True, required=True)
    upload_date = me.DateTimeField(default=datetime.datetime.now, required=True)
