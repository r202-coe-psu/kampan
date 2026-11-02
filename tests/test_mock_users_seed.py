import importlib.util
import pathlib

from kampan import models

_SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "seed_mock_users.py"
_spec = importlib.util.spec_from_file_location("seed_mock_users", _SCRIPT)
seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed)


def _real_org():
    real_user = models.User(
        first_name="Real", last_name="Person", email="real@example.com", username="realperson", roles=["admin"]
    )
    real_user.save()
    org = models.Organization(name="Real Org", status="active", created_by=real_user)
    org.save()
    division = models.Division(name="Real Division", organization=org, created_by=real_user)
    division.save()
    models.OrganizationUserRole(
        organization=org,
        user=real_user,
        division=division,
        roles=["admin"],
        added_by=real_user,
        last_modifier=real_user,
    ).save()
    return real_user, org


def test_seed_users_spread_and_idempotent(app):
    with app.app_context():
        created, skipped, users = seed.seed_users(100)
        assert (created, skipped, len(users)) == (100, 0, 100)
        assert models.User.objects(email__endswith="@mock.kampan.local").count() == 100
        assert len({u.username for u in users}) == 100
        assert all(len(u.username) >= 5 for u in users)
        assert models.User.objects(roles="admin").count() >= 3
        assert models.User.objects(roles__size=0).count() >= 3
        assert any(len(u.roles) > 1 for u in users)

        created, skipped, _ = seed.seed_users(100)
        assert (created, skipped) == (0, 100)
        assert models.User.objects().count() == 100


def test_seed_is_deterministic(app):
    with app.app_context():
        _, _, first = seed.seed_users(30)
        snapshot = [(u.email, u.first_name, u.last_name, tuple(u.roles)) for u in first]
        models.User.objects().delete()
        _, _, second = seed.seed_users(30)
        assert snapshot == [(u.email, u.first_name, u.last_name, tuple(u.roles)) for u in second]


def test_seed_organization_idempotent_and_clear_keeps_real_data(app):
    with app.app_context():
        real_user, org = _real_org()
        _, _, users = seed.seed_users(100)

        stats = seed.seed_organization(org, users)
        assert stats["members_created"] == 100 + seed.INVITE_COUNT
        statuses = {
            s: models.OrganizationUserRole.objects(organization=org, status=s).count()
            for s in ("active", "pending", "disactive")
        }
        assert statuses["pending"] == seed.INVITE_COUNT
        assert statuses["active"] > statuses["disactive"] > 0
        assert models.OrganizationUserRole.objects(organization=org, division=None).count() > 0
        assert models.Division.objects(organization=org).count() == len(seed.DIVISION_NAMES) + 1

        again = seed.seed_organization(org, users)
        assert again["members_created"] == 0
        assert again["divisions_created"] == 0
        total = models.OrganizationUserRole.objects(organization=org).count()
        assert total == 1 + 100 + seed.INVITE_COUNT

        result = seed.clear_mock()
        assert result["users_deleted"] == 100
        assert models.User.objects().count() == 1
        assert models.User.objects(id=real_user.id).first()
        assert models.OrganizationUserRole.objects().count() == 1
        divisions = models.Division.objects(organization=org)
        assert [d.name for d in divisions] == ["Real Division"]


def test_clear_keeps_division_still_used_by_real_member(app):
    with app.app_context():
        real_user, org = _real_org()
        _, _, users = seed.seed_users(10)
        seed.seed_organization(org, users, invites=0)
        mock_division = models.Division.objects(organization=org, description=seed.MOCK_DIVISION_DESCRIPTION).first()
        models.OrganizationUserRole(
            organization=org,
            user=real_user,
            division=mock_division,
            roles=["staff"],
            added_by=real_user,
            last_modifier=real_user,
        ).save()
        seed.clear_mock()
        assert models.Division.objects(id=mock_division.id).first()
