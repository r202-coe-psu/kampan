#!/usr/bin/env python3
"""
Script to generate requisition documents in MongoDB
Usage: python generate-requisitions.py [mongodb_host] [--count N]
"""

import sys
import mongoengine as me
import datetime
import random
from decimal import Decimal
from bson.objectid import ObjectId

from kampan import models
from kampan.models.requisitions import (
    Funds,
    Committees,
    RequisitionItem,
    ApprovalHistory,
)


# Sample data for generating realistic requisitions
PRODUCT_NAMES = [
    "เครื่องคอมพิวเตอร์โน้ตบุ๊ก",
    "เครื่องพิมพ์เลเซอร์",
    "โต๊ะทำงานสำนักงาน",
    "เก้าอี้สำนักงาน",
    "เครื่องปรับอากาศ",
    "เครื่องถ่ายเอกสาร",
    "โปรเจคเตอร์",
    "กระดานไวท์บอร์ด",
    "ตู้เก็บเอกสาร",
    "โทรศัพท์สำนักงาน",
    "เครื่องสแกนเอกสาร",
    "จอคอมพิวเตอร์",
    "เมาส์และคีย์บอร์ด",
    "ชั้นวางเอกสาร",
    "โคมไฟตั้งโต๊ะ",
]

COMPANIES = [
    "บริษัท เทคโนโลยี จำกัด",
    "บริษัท ออฟฟิศ ซัพพลาย จำกัด",
    "บริษัท เฟอร์นิเจอร์ โมเดิร์น จำกัด",
    "บริษัท อิเล็กทรอนิกส์ จำกัด",
    "บริษัท อุปกรณ์สำนักงาน จำกัด",
    "บริษัท คอมพิวเตอร์ ซัพพลาย จำกัด",
]

REASONS = [
    "เพื่อทดแทนอุปกรณ์เก่าที่ชำรุด",
    "เพื่อเพิ่มประสิทธิภาพการทำงาน",
    "เพื่อขยายสำนักงานใหม่",
    "เพื่อใช้ในโครงการพัฒนาระบบ",
    "เพื่อปรับปรุงสถานที่ทำงาน",
    "เพื่อรองรับพนักงานใหม่",
    "เพื่อเปลี่ยนอุปกรณ์ที่หมดอายุการใช้งาน",
]

CATEGORIES = [
    "material",
    "product",
    "service",
    "software",
]


def generate_requisition_items(count=None):
    """Generate random requisition items (1-4 items)"""
    if count is None:
        count = random.randint(1, 4)

    items = []
    selected_products = random.sample(PRODUCT_NAMES, min(count, len(PRODUCT_NAMES)))

    for product_name in selected_products:
        item = RequisitionItem(
            _id=ObjectId(),
            product_name=product_name,
            company=random.choice(COMPANIES),
            quantity=random.randint(1, 20),
            category=random.choice(CATEGORIES),
            amount=Decimal(str(random.randint(10000, 500000))),
            currency="THB",
        )
        items.append(item)

    return items


def generate_committees(org_user_roles):
    """Generate committee members"""
    if not org_user_roles or random.random() > 0.5:
        return []

    committees = []
    # Select 3-5 random members
    selected_members = random.sample(
        org_user_roles, min(random.randint(3, 5), len(org_user_roles))
    )

    committee_types = ["specification", "procurement", "inspection"]

    for i, member in enumerate(selected_members):
        committee = Committees(
            _id=ObjectId(),
            member=member,
            committee_type=random.choice(committee_types),
            committee_position="chairman" if i == 0 else "member",
        )
        committees.append(committee)

    return committees


def generate_approval_history(org_user_roles):
    """Generate approval history"""
    if not org_user_roles or random.random() > 0.3:
        return []

    history = []
    # Select 1-2 random approvers
    selected_approvers = random.sample(
        org_user_roles, min(random.randint(1, 2), len(org_user_roles))
    )

    for approver in selected_approvers:
        roles = approver.roles if approver.roles else ["staff"]
        approval = ApprovalHistory(
            _id=ObjectId(),
            approver=approver,
            approver_role=random.choice(roles),
            action="approved",
            reason=None,
            last_ip_address="127.0.0.1",
            user_agent="Mozilla/5.0",
            timestamp=datetime.datetime.now()
            - datetime.timedelta(days=random.randint(1, 30)),
        )
        history.append(approval)

    return history


def generate_funds(mas_list):
    """Generate fund allocation"""
    if not mas_list or random.random() > 0.6:
        return []

    funds = []
    # Select 1-2 random MAS projects
    selected_mas = random.sample(mas_list, min(random.randint(1, 2), len(mas_list)))

    for mas in selected_mas:
        fund = Funds(mas=mas, amount=Decimal(str(random.randint(50000, 300000))))
        funds.append(fund)

    return funds


def create_requisition(
    organization, purchaser, manager, mas_list, creator, status=None
):
    """Create a single requisition document"""

    # Get organization user roles for committees and approvals
    org_user_roles = list(
        models.OrganizationUserRole.objects(
            organization=organization, status="active"
        ).limit(10)
    )

    items = generate_requisition_items()
    committees = generate_committees(org_user_roles)
    approval_history = generate_approval_history(org_user_roles)
    funds = generate_funds(mas_list)

    # Random start date within the last 90 days
    start_date = datetime.datetime.now() - datetime.timedelta(
        days=random.randint(0, 90)
    )

    # Random status if not provided
    if status is None:
        status = random.choice(["pending", "progress", "complete", "cancelled"])

    requisition = models.Requisition(
        purchaser=purchaser,
        manager=manager,
        phone=f"0{random.randint(800000000, 999999999)}",
        reason=random.choice(REASONS),
        start_date=start_date,
        items=items,
        committees=committees,
        approval_history=approval_history,
        status=status,
        type="general",
        fund=funds,
        created_by=creator,
        last_updated_by=creator,
        created_date=start_date,
    )

    return requisition


def generate_requisitions(count=10, organization_id=None):
    """
    Generate multiple requisition documents

    Args:
        count: Number of requisitions to generate
        organization_id: Specific organization ID (optional)
    """

    # Get or create organization
    if organization_id:
        organization = models.Organization.objects(
            id=organization_id, status="active"
        ).first()
        if not organization:
            print(f"Organization with ID {organization_id} not found")
            return
    else:
        organization = models.Organization.objects(status="active").first()
        if not organization:
            print("No active organization found. Creating one...")
            user = models.User.objects.first()
            if not user:
                print("No user found. Please create a user first.")
                return

            organization = models.Organization(
                name="องค์กรทดสอบ",
                description="องค์กรสำหรับทดสอบระบบ",
                status="active",
                created_by=user,
                last_updated_by=user,
            )
            organization.save()
            print(f"Created organization: {organization.name}")

    # Get users
    creator = models.User.objects.first()
    if not creator:
        print("No user found. Please create a user first.")
        return

    # Get organization user roles
    org_user_roles = list(
        models.OrganizationUserRole.objects(organization=organization, status="active")
    )

    if not org_user_roles:
        print("No organization user roles found. Creating some...")
        # Create organization user roles
        users = list(models.User.objects().limit(5))
        if not users:
            print("No users found. Please create users first.")
            return

        for user in users:
            org_role = models.OrganizationUserRole(
                organization=organization,
                user=user,
                roles=["staff"],
                first_name=user.first_name,
                last_name=user.last_name,
                email=user.email,
                status="active",
                added_by=creator,
                last_modifier=creator,
            )
            org_role.save()
            org_user_roles.append(org_role)

        print(f"Created {len(org_user_roles)} organization user roles")

    # Get MAS projects
    mas_list = list(models.MAS.objects(status="active").limit(5))
    if not mas_list:
        print(
            "No MAS projects found. Requisitions will be created without fund allocation."
        )

    # Generate requisitions
    created_count = 0
    failed_count = 0

    print(f"\nGenerating {count} requisitions...")
    print(f"Organization: {organization.name}")
    print(f"Available user roles: {len(org_user_roles)}")
    print(f"Available MAS projects: {len(mas_list)}")
    print("-" * 60)

    for i in range(count):
        try:
            purchaser = random.choice(org_user_roles)
            manager = random.choice(org_user_roles) if len(org_user_roles) > 1 else None

            requisition = create_requisition(
                organization=organization,
                purchaser=purchaser,
                manager=manager,
                mas_list=mas_list,
                creator=creator,
            )

            requisition.save()
            created_count += 1

            print(
                f"✓ Created requisition {i+1}/{count}: {requisition.requisition_code}"
            )
            print(f"  - Purchaser: {purchaser.display_fullname()}")
            print(f"  - Items: {len(requisition.items)}")
            print(f"  - Status: {requisition.status}")
            print(
                f"  - Total amount: {sum(item.amount for item in requisition.items):,.2f} THB"
            )

        except Exception as e:
            failed_count += 1
            print(f"✗ Failed to create requisition {i+1}/{count}: {str(e)}")

    print("-" * 60)
    print(f"\nSummary:")
    print(f"  Successfully created: {created_count}")
    print(f"  Failed: {failed_count}")
    print(f"  Total: {count}")

    return created_count


def main():
    """Main function"""
    # Parse arguments
    mongodb_host = "mongodb://localhost:27017/kampandb"
    count = 10
    organization_id = None

    if len(sys.argv) > 1:
        if sys.argv[1] == "--help" or sys.argv[1] == "-h":
            print(__doc__)
            print("\nOptions:")
            print(
                "  mongodb_host          MongoDB connection string (default: localhost:27017)"
            )
            print(
                "  --count N            Number of requisitions to generate (default: 10)"
            )
            print("  --org ORG_ID         Specific organization ID (optional)")
            print("\nExamples:")
            print("  # Local development (default):")
            print("  python generate-requisitions.py")
            print("  python generate-requisitions.py --count 20")
            print()
            print("  # Docker environment:")
            print("  docker-compose exec web python scripts/generate-requisitions.py")
            print(
                "  python generate-requisitions.py mongodb://mongodb:27017/kampandb --count 50"
            )
            print()
            print("  # With specific organization:")
            print(
                "  python generate-requisitions.py --count 50 --org 507f1f77bcf86cd799439011"
            )
            return

        # Parse arguments
        i = 1
        while i < len(sys.argv):
            arg = sys.argv[i]
            if arg == "--count":
                if i + 1 < len(sys.argv):
                    count = int(sys.argv[i + 1])
                    i += 2
                else:
                    print("Error: --count requires a number")
                    return
            elif arg == "--org":
                if i + 1 < len(sys.argv):
                    organization_id = sys.argv[i + 1]
                    i += 2
                else:
                    print("Error: --org requires an organization ID")
                    return
            else:
                mongodb_host = arg
                i += 1

    # Connect to MongoDB
    print(f"Connecting to MongoDB: {mongodb_host}")
    try:
        me.connect(host=mongodb_host, serverSelectionTimeoutMS=5000)
        # Test connection
        me.get_db().client.server_info()
        print("✓ Connected successfully")
    except Exception as e:
        print(f"✗ Failed to connect to MongoDB: {str(e)}")
        print("\nTroubleshooting:")
        print("  - Make sure MongoDB is running")
        print(
            "  - For local development: python generate-requisitions.py mongodb://localhost:27017/kampandb"
        )
        print(
            "  - For Docker: docker-compose exec web python scripts/generate-requisitions.py"
        )
        print(
            "  - Or specify host: python generate-requisitions.py mongodb://mongodb:27017/kampandb"
        )
        return

    # Generate requisitions
    try:
        generate_requisitions(count=count, organization_id=organization_id)
    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
