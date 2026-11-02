#!/usr/bin/env python3
"""
Seed mock users (and optionally organization members / divisions) so the
organization management pages and the global user-role dashboard can be tried
with realistic volume on a local dev database.

Usage:
    python scripts/seed_mock_users.py [--host URI] [--db NAME] [--count N]
                                      [--organization-id ID] [--seed N]
    python scripts/seed_mock_users.py [--host URI] [--db NAME] --clear

Everything created is identifiable by the mock marker: users have an email
ending in "@mock.kampan.local"; divisions created by this script have the
description "[mock-seed]". `--clear` deletes only those rows.

The script is idempotent (existing mock users / memberships are skipped) and
deterministic (seeded random).
"""

import argparse
import datetime
import os
import random
import sys

import mongoengine as me

MOCK_EMAIL_DOMAIN = "mock.kampan.local"
MOCK_DIVISION_DESCRIPTION = "[mock-seed]"
DEFAULT_COUNT = 100
DEFAULT_SEED = 2569
INVITE_COUNT = 12

# (thai, romanized)
FIRST_NAMES = [
    ("สมชาย", "Somchai"),
    ("สมหญิง", "Somying"),
    ("ประเสริฐ", "Prasert"),
    ("วิชัย", "Wichai"),
    ("สุรชัย", "Surachai"),
    ("อนุชา", "Anucha"),
    ("ธนากร", "Thanakorn"),
    ("กิตติพงษ์", "Kittipong"),
    ("ณัฐพล", "Natthaphon"),
    ("ปิยะ", "Piya"),
    ("สุพจน์", "Supot"),
    ("นพดล", "Nopphadon"),
    ("ศิริพร", "Siriporn"),
    ("วรรณา", "Wanna"),
    ("จันทร์เพ็ญ", "Janpen"),
    ("พิมพ์ใจ", "Pimjai"),
    ("กัลยา", "Kanlaya"),
    ("นภาพร", "Napaporn"),
    ("อรุณี", "Arunee"),
    ("สุดารัตน์", "Sudarat"),
    ("ชลธิชา", "Chonticha"),
    ("รัตนา", "Rattana"),
    ("มานะ", "Mana"),
    ("บุญเรือน", "Boonruen"),
    ("อภิชาติ", "Apichat"),
    ("ชัยวัฒน์", "Chaiwat"),
    ("พรทิพย์", "Pornthip"),
    ("ปรียา", "Priya"),
    ("เกษม", "Kasem"),
    ("ดวงใจ", "Duangjai"),
]
LAST_NAMES = [
    ("ใจดี", "Jaidee"),
    ("สุขสวัสดิ์", "Suksawat"),
    ("รักษา", "Raksa"),
    ("แก้วมณี", "Kaewmanee"),
    ("ทองคำ", "Thongkham"),
    ("มั่นคง", "Mankhong"),
    ("เจริญสุข", "Charoensuk"),
    ("พงษ์พานิช", "Phongphanit"),
    ("ศรีสุข", "Srisuk"),
    ("บุญมี", "Boonmee"),
    ("วงศ์สวัสดิ์", "Wongsawat"),
    ("ชูเกียรติ", "Chukiat"),
    ("สมบูรณ์", "Somboon"),
    ("ปัญญา", "Panya"),
    ("นาคสุข", "Naksuk"),
    ("เพชรรัตน์", "Phetrat"),
    ("ดวงจันทร์", "Duangchan"),
    ("หอมหวล", "Homhuan"),
    ("สุวรรณ", "Suwan"),
    ("คงเจริญ", "Khongcharoen"),
    ("ไชยวงศ์", "Chaiwong"),
    ("เรืองศรี", "Ruangsri"),
    ("มณีรัตน์", "Maneerat"),
    ("พรหมมา", "Phromma"),
]

# System-level (User.roles) distribution for 100 users; scaled by --count.
USER_ROLE_PATTERN = (
    [["user"]] * 24
    + [["staff"]] * 22
    + [["student"]] * 20
    + [["lecturer"]] * 11
    + [["supervisor"]] * 4
    + [["admin"]] * 2
    + [["staff", "supervisor"]] * 3
    + [["lecturer", "supervisor"]] * 2
    + [["admin", "staff"]] * 1
    + [["user", "student"]] * 3
    + [[]] * 8
)

DIVISION_NAMES = [
    "ฝ่ายบริหารทั่วไป",
    "ฝ่ายพัสดุและครุภัณฑ์",
    "ฝ่ายการเงินและบัญชี",
    "ฝ่ายบุคคล",
    "ฝ่ายเทคโนโลยีสารสนเทศ",
    "ฝ่ายอาคารสถานที่",
    "ฝ่ายวิชาการ",
]

APPOINTMENTS = [
    "",
    "",
    "",
    "นักวิชาการพัสดุ",
    "เจ้าหน้าที่บริหารงานทั่วไป",
    "นักวิชาการเงินและบัญชี",
    "นักวิชาการคอมพิวเตอร์",
    "พนักงานขับรถยนต์",
    "หัวหน้าฝ่าย",
    "ผู้ช่วยหัวหน้าฝ่าย",
    "นักทรัพยากรบุคคล",
]


def mock_email(index):
    return f"mock.user{index:03d}@{MOCK_EMAIL_DOMAIN}"


def invite_email(index):
    return f"mock.invite{index:03d}@{MOCK_EMAIL_DOMAIN}"


def _mock_user_query():
    return me.Q(email__endswith="@" + MOCK_EMAIL_DOMAIN)


def _pick_org_roles(rng):
    r = rng.random()
    if r < 0.58:
        return ["staff"]
    if r < 0.68:
        return ["endorser"]
    if r < 0.74:
        return ["head"]
    if r < 0.78:
        return ["supervisor supplier"]
    if r < 0.82:
        return ["admin"]
    if r < 0.87:
        return ["driver"]
    if r < 0.89:
        return ["director"]
    if r < 0.91:
        return ["manager"]
    if r < 0.96:
        return ["staff", "endorser"]
    return ["endorser", "head"]


def seed_users(count=DEFAULT_COUNT, seed=DEFAULT_SEED):
    """Create mock users; skip those that already exist. Returns (created, skipped, users)."""
    from kampan import models

    rng = random.Random(seed)
    pattern = list(USER_ROLE_PATTERN)
    rng.shuffle(pattern)
    now = datetime.datetime.now()

    created = skipped = 0
    users = []
    for i in range(1, count + 1):
        # Draw random values unconditionally so a re-run (or a bigger --count)
        # yields the same data per index regardless of what already exists.
        first_th, first_en = rng.choice(FIRST_NAMES)
        last_th, last_en = rng.choice(LAST_NAMES)
        roles = list(pattern[(i - 1) % len(pattern)])
        created_days_ago = rng.randint(1, 400)
        login_days_ago = rng.randint(0, 60) if rng.random() < 0.8 else None
        student_id = "%02d%08d" % (rng.randint(63, 69), rng.randint(0, 99999999))

        email = mock_email(i)
        user = models.User.objects(email=email).first()
        if user:
            skipped += 1
            users.append(user)
            continue

        user = models.User(
            username=f"mock.user{i:03d}",
            email=email,
            first_name=first_en,
            last_name=last_en,
            status="active",
            roles=roles,
            created_date=now - datetime.timedelta(days=created_days_ago),
            last_login_date=(
                now - datetime.timedelta(days=login_days_ago, hours=rng.randint(0, 23))
                if login_days_ago is not None
                else None
            ),
            resources={
                "psu": {
                    "display_name_th": f"{first_th} {last_th}",
                    "display_name": f"{first_en} {last_en}",
                    "first_name_th": first_th,
                    "last_name_th": last_th,
                }
            },
        )
        if "student" in roles:
            user.student_id = student_id
        user.save()
        created += 1
        users.append(user)
    return created, skipped, users


def seed_organization(organization, users, seed=DEFAULT_SEED, invites=INVITE_COUNT):
    """Create divisions and memberships for the given organization.

    Returns a dict of counters.
    """
    from kampan import models

    rng = random.Random(seed + 1)
    actor = users[0] if users else None
    if actor is None:
        raise ValueError("no mock users available to act as creator")

    stats = {"divisions_created": 0, "members_created": 0, "members_skipped": 0}

    divisions = []
    for name in DIVISION_NAMES:
        division = models.Division.objects(organization=organization, name=name).first()
        if not division:
            division = models.Division(
                name=name,
                description=MOCK_DIVISION_DESCRIPTION,
                status="active",
                organization=organization,
                created_by=actor,
                last_updated_by=actor,
            )
            division.save()
            stats["divisions_created"] += 1
        divisions.append(division)

    now = datetime.datetime.now()

    def make_row(user, email, first_name, last_name, status):
        roles = _pick_org_roles(rng)
        # ~12% have no division; the rest are weighted towards the first divisions.
        division = None
        if rng.random() >= 0.12:
            division = rng.choices(divisions, weights=[8, 7, 5, 4, 6, 3, 3][: len(divisions)])[0]
        appointment = rng.choice(APPOINTMENTS)
        created_days_ago = rng.randint(1, 300)
        return roles, division, appointment, now - datetime.timedelta(days=created_days_ago)

    for index, user in enumerate(users, start=1):
        # ~5% removed ("disactive"), the rest active.
        status = "disactive" if rng.random() < 0.05 else "active"
        roles, division, appointment, created = make_row(
            user, user.email, user.first_name, user.last_name, status
        )
        if models.OrganizationUserRole.objects(organization=organization, user=user).first():
            stats["members_skipped"] += 1
            continue
        models.OrganizationUserRole(
            organization=organization,
            division=division,
            user=user,
            roles=roles,
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
            appointment=appointment,
            status=status,
            added_by=actor,
            last_modifier=actor,
            created_date=created,
        ).save()
        stats["members_created"] += 1
        if status == "active" and not user.user_setting.current_organization:
            user.user_setting.current_organization = organization
            user.save()

    # Pending invitations: members added by email who have not logged in yet.
    for n in range(1, invites + 1):
        first_th, first_en = rng.choice(FIRST_NAMES)
        last_th, last_en = rng.choice(LAST_NAMES)
        email = invite_email(n)
        roles, division, appointment, created = make_row(None, email, first_en, last_en, "pending")
        if models.OrganizationUserRole.objects(organization=organization, email=email).first():
            stats["members_skipped"] += 1
            continue
        models.OrganizationUserRole(
            organization=organization,
            division=division,
            user=None,
            roles=roles,
            first_name=first_en,
            last_name=last_en,
            email=email,
            appointment=appointment,
            status="pending",
            added_by=actor,
            last_modifier=actor,
            created_date=created,
        ).save()
        stats["members_created"] += 1

    return stats


def clear_mock():
    """Delete only mock-marked data (in every organization). Returns a dict of counters."""
    from kampan import models

    mock_users = models.User.objects(_mock_user_query())
    mock_user_ids = list(mock_users.scalar("id"))

    role_query = me.Q(email__endswith="@" + MOCK_EMAIL_DOMAIN) | me.Q(user__in=mock_user_ids)
    roles_deleted = models.OrganizationUserRole.objects(role_query).delete()

    # Divisions created by this script, only if nothing real still points to them.
    division_query = me.Q(description=MOCK_DIVISION_DESCRIPTION, created_by__in=mock_user_ids)
    divisions_deleted = 0
    for division in models.Division.objects(division_query):
        if models.OrganizationUserRole.objects(division=division).count() == 0:
            division.delete()
            divisions_deleted += 1

    users_deleted = mock_users.delete()
    return {
        "members_deleted": roles_deleted,
        "divisions_deleted": divisions_deleted,
        "users_deleted": users_deleted,
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--host",
        default=os.environ.get("MONGODB_HOST") or "mongodb://localhost:27017",
        help="MongoDB host or URI (default: $MONGODB_HOST or mongodb://localhost:27017)",
    )
    parser.add_argument("--db", default=os.environ.get("MONGODB_DB") or "kampandb")
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT, help="number of mock users")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--organization-id",
        help="attach mock users to this organization (creates divisions + memberships)",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="delete the mock users/memberships/divisions instead of creating them",
    )
    return parser.parse_args(argv)


def run(args):
    from kampan import models

    organization = None
    if args.organization_id:
        organization = models.Organization.objects(id=args.organization_id).first()
        if not organization:
            print(f"Organization {args.organization_id} not found", file=sys.stderr)
            return 1

    if args.clear:
        result = clear_mock()
        print("Cleared:", result)
        return 0

    created, skipped, users = seed_users(args.count, args.seed)
    print(f"Users: {created} created, {skipped} already existed")
    if organization:
        stats = seed_organization(organization, users, args.seed)
        print(f"Organization '{organization.name}':", stats)
    return 0


def main(argv=None):
    args = parse_args(argv)
    me.connect(db=args.db, host=args.host)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
