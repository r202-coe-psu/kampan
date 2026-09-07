"""
MongoDB Backup Script

Supports full backup (using mongodump) or time-filtered backup (using PyMongo & BSON).

Usage examples:
    Interactive mode:
        python scripts/backup-mongodb.py

    CLI mode:
        python scripts/backup-mongodb.py --period all
        python scripts/backup-mongodb.py --period 1m
        python scripts/backup-mongodb.py --period 3m
        python scripts/backup-mongodb.py -p 6m
        python scripts/backup-mongodb.py -p 1y

    Available period choices:
        1, all : ทั้งหมด (All Data)
        2, 1m  : ก่อน 1 เดือน (Past 1 Month)
        3, 2m  : ก่อน 2 เดือน (Past 2 Months)
        4, 3m  : ก่อน 3 เดือน (Past 3 Months)
        5, 6m  : ก่อน 6 เดือน (Past 6 Months)
        6, 1y  : ก่อน 1 ปี (Past 1 Year)

How to restore the backup:
    For Full Backup (.archive.gz):
        mongorestore --uri="mongodb://localhost:27017/kampandb" --archive=backups/kampandb_backup_YYYYMMDD_HHMMSS_all.archive.gz --gzip --drop

    For Filtered Backup (.tar.gz):
        tar -xzf backups/kampandb_backup_YYYYMMDD_HHMMSS_1m.tar.gz -C backups/
        mongorestore --uri="mongodb://localhost:27017/kampandb" --gzip --drop backups/kampandb_backup_YYYYMMDD_HHMMSS_1m/kampandb
"""

import argparse
import datetime
import gzip
import json
import os
import shutil
import subprocess
import sys
import tarfile
import threading
import time
from typing import Any

import bson
from dotenv import load_dotenv
from pymongo import MongoClient

# Metadata collections that should always be backed up in full regardless of time period filter
METADATA_COLLECTIONS = {
    "users",
    "stations",
    "system_settings",
    "forecast_models",
    "hotspot_source_files",
    "climate_formulas",
    "caches",
    "tokens",
}

PERIOD_MAPPING: dict[str, dict[str, Any]] = {
    "1": {"code": "all", "label": "ทั้งหมด (All Data)", "days": None},
    "2": {"code": "1m", "label": "ก่อน 1 เดือน (Past 1 Month)", "days": 30},
    "3": {"code": "2m", "label": "ก่อน 2 เดือน (Past 2 Months)", "days": 60},
    "4": {"code": "3m", "label": "ก่อน 3 เดือน (Past 3 Months)", "days": 90},
    "5": {"code": "6m", "label": "ก่อน 6 เดือน (Past 6 Months)", "days": 180},
    "6": {"code": "1y", "label": "ก่อน 1 ปี (Past 1 Year)", "days": 365},
}

CODE_TO_OPTION: dict[str, str] = {v["code"]: k for k, v in PERIOD_MAPPING.items()}


def backup_mongodb_full(mongodb_uri: str) -> None:
    """Performs a full database backup using standard `mongodump`."""
    backup_dir = os.path.abspath("backups")
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = os.path.join(
        backup_dir, f"kampandb_backup_{timestamp}_all.archive.gz"
    )

    print("=" * 60)
    print("Starting MongoDB full backup (mongodump)...")
    print(f"Destination: {backup_filename}")
    print("=" * 60)

    command = [
        "mongodump",
        "--uri",
        mongodb_uri,
        f"--archive={backup_filename}",
        "--gzip",
    ]

    event = threading.Event()

    def progress_monitor() -> None:
        chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        i = 0
        while not event.is_set():
            size_mb = 0.0
            if os.path.exists(backup_filename):
                size_mb = os.path.getsize(backup_filename) / (1024 * 1024)
            sys.stdout.write(
                f"\r\033[K[ {chars[i % len(chars)]} ] Backing up... Archive size: {size_mb:.2f} MB"
            )
            sys.stdout.flush()
            time.sleep(0.1)
            i += 1

    t = threading.Thread(target=progress_monitor)
    t.start()

    try:
        subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        event.set()
        t.join()

        sys.stdout.write("\r\033[K")
        print("✅ Full backup completed successfully!")
        print(f"📁 Backup saved to: {backup_filename}")

        file_size_bytes = os.path.getsize(backup_filename)
        file_size_mb = file_size_bytes / (1024 * 1024)
        print(f"📦 File size: {file_size_mb:.2f} MB")
        print("-" * 60)
        print("💡 Restore Command:")
        print(
            f'   mongorestore --uri="{mongodb_uri}" --archive={backup_filename} --gzip --drop'
        )
        print("=" * 60)

    except subprocess.CalledProcessError as e:
        event.set()
        t.join()
        sys.stdout.write("\r\033[K")
        print("\n❌ Backup failed!")
        print("Error Output:")
        print(e.stderr)

    except FileNotFoundError:
        event.set()
        t.join()
        sys.stdout.write("\r\033[K")
        print("\n❌ Error: 'mongodump' command not found.")
        print("Please ensure MongoDB Database Tools are installed.")


def backup_mongodb_filtered(
    mongodb_uri: str, period_code: str, period_info: dict[str, Any]
) -> None:
    """Performs a time-filtered database backup using PyMongo and BSON export."""
    client: MongoClient = MongoClient(mongodb_uri)
    db = client.get_database()
    db_name = db.name or "kampandb"

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_folder_name = f"kampandb_backup_{timestamp}_{period_code}"
    backup_dir = os.path.abspath("backups")
    os.makedirs(backup_dir, exist_ok=True)

    temp_dump_dir = os.path.join(backup_dir, backup_folder_name)
    target_db_dir = os.path.join(temp_dump_dir, db_name)
    os.makedirs(target_db_dir, exist_ok=True)

    archive_filename = os.path.join(backup_dir, f"{backup_folder_name}.tar.gz")

    days = period_info["days"]
    cutoff_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        days=days
    )

    # ObjectId matching cutoff timestamp
    cutoff_oid_hex = f"{int(cutoff_date.timestamp()):08x}0000000000000000"
    cutoff_oid = bson.ObjectId(cutoff_oid_hex)

    print("=" * 60)
    print("Starting MongoDB filtered backup...")
    print(f"Period: {period_info['label']}")
    print(f"Cutoff Date: >= {cutoff_date.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Destination: {archive_filename}")
    print("=" * 60)

    collections = [c for c in db.list_collection_names() if not c.startswith("system.")]

    total_docs = 0

    for col_name in collections:
        col = db[col_name]
        is_metadata = col_name in METADATA_COLLECTIONS

        if is_metadata:
            query: dict[str, Any] = {}
        else:
            query = {
                "$or": [
                    {"timestamp": {"$gte": cutoff_date}},
                    {"created_at": {"$gte": cutoff_date}},
                    {"acq_date": {"$gte": cutoff_date}},
                    {"date": {"$gte": cutoff_date}},
                    {"datetime": {"$gte": cutoff_date}},
                    {"_id": {"$gte": cutoff_oid}},
                ]
            }

        bson_path = os.path.join(target_db_dir, f"{col_name}.bson.gz")
        meta_path = os.path.join(target_db_dir, f"{col_name}.metadata.json")

        doc_count = 0
        cursor = col.find(query)

        with gzip.open(bson_path, "wb") as f:
            for doc in cursor:
                f.write(bson.encode(doc))
                doc_count += 1

        # Save collection index metadata
        try:
            indexes = [dict(idx) for idx in col.list_indexes()]
        except Exception:
            indexes = [{"v": 2, "key": {"_id": 1}, "name": "_id_"}]

        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump({"indexes": indexes}, f, default=str)

        total_docs += doc_count
        note = " (Metadata)" if is_metadata else ""
        print(f"  📦 Collection '{col_name}': {doc_count:,} documents{note}")

    print("-" * 60)
    print("Compressing backup archive...")
    with tarfile.open(archive_filename, "w:gz") as tar:
        tar.add(temp_dump_dir, arcname=backup_folder_name)

    shutil.rmtree(temp_dump_dir)

    file_size_mb = os.path.getsize(archive_filename) / (1024 * 1024)
    print("=" * 60)
    print("✅ Filtered backup completed successfully!")
    print(f"📁 Backup saved to: {archive_filename}")
    print(f"📦 File size: {file_size_mb:.2f} MB ({total_docs:,} total documents)")
    print("-" * 60)
    print("💡 To restore this backup, run:")
    print(f"   1. tar -xzf {archive_filename} -C {backup_dir}/")
    print(
        f'   2. mongorestore --uri="{mongodb_uri}" --gzip --drop {os.path.join(backup_dir, backup_folder_name, db_name)}'
    )
    print("=" * 60)


def prompt_period_choice() -> str:
    """Prompts the user to interactively select a backup period."""
    print("=" * 60)
    print("📌 กรุณาเลือกช่วงเวลาที่ต้องการสำรองข้อมูล (Backup Period):")
    print("=" * 60)
    for key, val in PERIOD_MAPPING.items():
        print(f"  [{key}] {val['label']}")
    print("-" * 60)

    choice = input("เลือกตัวเลือก (1-6) [ default: 1 ]: ").strip()
    if not choice:
        choice = "1"

    if choice not in PERIOD_MAPPING:
        # Check if user typed period code directly (e.g. 1m, 3m)
        if choice in CODE_TO_OPTION:
            choice = CODE_TO_OPTION[choice]
        else:
            print("⚠️  ตัวเลือกไม่ถูกต้อง เลือกใช้ค่าเริ่มต้น: ทั้งหมด (All Data)")
            choice = "1"

    return choice


def backup_mongodb(period: str | None = None) -> None:
    """Main backup function entry point."""
    load_dotenv()
    mongodb_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017/kampandb")

    selected_option = "1"

    if period:
        p_lower = period.lower().strip()
        if p_lower in PERIOD_MAPPING:
            selected_option = p_lower
        elif p_lower in CODE_TO_OPTION:
            selected_option = CODE_TO_OPTION[p_lower]
        else:
            print(f"⚠️  ไม่รู้จักช่วงเวลา '{period}' เลือกใช้ค่าเริ่มต้น: ทั้งหมด (All Data)")
            selected_option = "1"
    else:
        # Interactive prompt if sys.stdin is TTY, else default to 'all'
        if sys.stdin.isatty():
            selected_option = prompt_period_choice()
        else:
            selected_option = "1"

    period_info = PERIOD_MAPPING[selected_option]

    if period_info["code"] == "all":
        backup_mongodb_full(mongodb_uri)
    else:
        backup_mongodb_filtered(mongodb_uri, period_info["code"], period_info)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="MongoDB Backup Script with Time Period Selection"
    )
    parser.add_argument(
        "-p",
        "--period",
        type=str,
        choices=["1", "2", "3", "4", "5", "6", "all", "1m", "2m", "3m", "6m", "1y"],
        help="Specify backup period (all, 1m, 2m, 3m, 6m, 1y)",
    )
    args = parser.parse_args()

    backup_mongodb(period=args.period)
