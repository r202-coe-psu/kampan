import sys
import mongoengine as me

# import pandas as pd
from kampan import models
import datetime
import calendar


def update_snapshot():

    snapshots = models.ItemSnapshot.objects()
    for snapshot in snapshots:
        snapshot.update_data()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        me.connect(db="kampandb", host=sys.argv[1])
    else:
        me.connect(db="kampandb")
    update_snapshot()
