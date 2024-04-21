import sys
import mongoengine as me

# import pandas as pd
from kampan import models
import datetime


def check_has_email_template():
    print("Checking has email template")
    organizations = models.Organization.objects()
    for organization in organizations:
        email_template = organization.get_default_email_template()
        if not email_template:
            return False
    print("There is a email template.")
    return True


def create_user_email_template():
    print("start create email template")
    organizations = models.Organization.objects()
    for organization in organizations:
        email_template = organization.get_default_email_template()
        if not email_template:
            email_template = models.EmailTemplate(
                name="รูปแบบเริ่มต้น",
                subject="ขอเบิกอุปกรณ์",
                body="""เรียน  {{ endorser_name }} 
ข้าพเจ้า {{ user_name }} แผนก{{ division_name }}  ขอแจ้งความประสงค์เพื่อเบิกอุปกรณ์
เหตุผลการเบิก:  {{ order_desscription }}
ตรวจสอบรายละเอียดที่: {{ endorsement_url }}


จึงเรียนมาเพื่อโปรดพิจารณา

ขอแสดงความนับถือ

{{ user_name }} 
""",
                type="participant",
                organization=organization,
                is_default=True,
            )
            email_template.save()
    print("finish")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        me.connect(db="kampandb", host=sys.argv[1])
    else:
        me.connect(db="kampandb")
    print("start create")
    if not check_has_email_template():
        create_user_email_template()

    print("end create")
