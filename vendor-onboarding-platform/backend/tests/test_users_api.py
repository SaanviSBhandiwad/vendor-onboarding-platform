from tests.conftest import auth

NEW_OPS = {"email": "reviewer@company.in", "full_name": "Rita Reviewer", "password": "Rev1ewer99", "role": "OPERATIONS"}


def test_admin_creates_operations_user(client, admin_user):
    r = client.post("/api/v1/users", json=NEW_OPS, headers=auth(admin_user))
    assert r.status_code == 201 and r.json()["role"] == "OPERATIONS"


def test_non_admins_cannot_manage_users(client, ops_user, vendor_user):
    for user in (ops_user, vendor_user):
        assert client.post("/api/v1/users", json=NEW_OPS, headers=auth(user)).status_code == 403
        r = client.get("/api/v1/users", headers=auth(user))
        assert r.status_code == 403
        assert r.json()["error"]["details"]["required_roles"] == ["ADMIN"]


def test_admin_lists_and_filters_users(client, admin_user, ops_user, vendor_user):
    all_users = client.get("/api/v1/users", headers=auth(admin_user)).json()
    assert all_users["total"] == 3
    ops = client.get("/api/v1/users", params={"role": "OPERATIONS"}, headers=auth(admin_user)).json()
    assert [u["id"] for u in ops["items"]] == [str(ops_user.id)]


def test_admin_changes_role_and_it_is_audited(client, admin_user, ops_user, db_session):
    r = client.patch(f"/api/v1/users/{ops_user.id}", json={"role": "ADMIN"}, headers=auth(admin_user))
    assert r.status_code == 200 and r.json()["role"] == "ADMIN"
    from app.services import audit_service
    logs = audit_service.list_for_entity(db_session, "user", ops_user.id)
    assert logs[-1].action == "user_updated"
    assert logs[-1].details == {"before": {"role": "OPERATIONS"}, "after": {"role": "ADMIN"}}
    assert logs[-1].actor == f"user:{admin_user.id}"


def test_admin_cannot_lock_themselves_out(client, admin_user):
    for change in ({"is_active": False}, {"role": "OPERATIONS"}):
        r = client.patch(f"/api/v1/users/{admin_user.id}", json=change, headers=auth(admin_user))
        assert r.status_code == 409 and r.json()["error"]["code"] == "self_lockout"


def test_update_unknown_user_404(client, admin_user):
    r = client.patch("/api/v1/users/00000000-0000-0000-0000-000000000000", json={"is_active": False},
                     headers=auth(admin_user))
    assert r.status_code == 404


def test_create_admin_script(db_session, monkeypatch, capsys):
    from app.scripts import create_admin
    monkeypatch.setattr(create_admin, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)
    args = ["--email", "Boss@Company.in", "--password", "Adm1npass"]
    assert create_admin.main(args) == 0
    assert "Admin created: boss@company.in" in capsys.readouterr().out
    assert create_admin.main(args) == 1  # duplicate
    assert create_admin.main(["--email", "x@company.in", "--password", "weak"]) == 1
