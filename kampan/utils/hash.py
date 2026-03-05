import hmac
import hashlib
import json
from flask import current_app

SALT = "kampan_encryption_salt".encode("utf-8")


def hash_mongo_metadata(metadata_dict):
    salted_data = SALT + str(metadata_dict).encode("utf-8")
    hashed_data = hashlib.sha256(salted_data)
    return hashed_data.hexdigest()
