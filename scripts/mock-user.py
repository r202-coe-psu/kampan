import sys
import mongoengine as me

# import pandas as pd
from kampan import models
import datetime


def check_has_user_admin_and_reset_pwd():
    print("Checking has user tester")
    user = models.User.objects(username="test1").first()
    if user:
        print("There is a user test.")
        return True
    return False


def create_user_admin():
    print("start create tester")
    for i in range(5):
        user = models.User(
            username="test" + str(i),
            password="",
            email=f"test{i}@gmail.com",
            first_name="test" + str(i),
            last_name="system",
            roles=["user"],
            status="active",
        )
        user.save()
    print("finish")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        me.connect(db="kampandb", host=sys.argv[1])
    else:
        me.connect(db="kampandb")
    print("start create")
    if not check_has_user_admin_and_reset_pwd():
        create_user_admin()

    print("end create")
