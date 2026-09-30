from app.core.security import create_access_token
from tests.conftest import PASSWORD, auth

REGISTER = {"email": "New.Vendor@Example.com", "full_name": "New Vendor", "password": "Str0ngpass"}


def login(client, email, password=PASSWORD):
    return client.post("/api/v1/auth/login", data={"username": email, "password": password})


def test_register_creates_vendor_account(client):
    r = client.post("/api/v1/auth/register", json=REGISTER)
    assert r.status_code == 201
    body = r.json()
    assert body["role"] == "VENDOR"
    assert body["email"] == "new.vendor@example.com"
    assert "password" not in body and "hashed_password" not in body


def test_register_cannot_choose_role(client):
    r = client.post("/api/v1/auth/register", json={**REGISTER, "role": "ADMIN"})
    assert r.status_code == 422
    assert r.json()["error"]["details"]["errors"][0]["field"] == "role"


def test_register_duplicate_email_case_insensitive(client):
    client.post("/api/v1/auth/register", json=REGISTER)
    r = client.post("/api/v1/auth/register", json={**REGISTER, "email": "NEW.VENDOR@example.com"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "duplicate_user"


def test_register_rejects_weak_password(client):
    for pw in ["short1", "onlyletters", "12345678"]:
        r = client.post("/api/v1/auth/register", json={**REGISTER, "password": pw})
        assert r.status_code == 422, pw


def test_register_then_login_then_me(client):
    client.post("/api/v1/auth/register", json=REGISTER)
    r = login(client, "new.vendor@example.com", "Str0ngpass")
    assert r.status_code == 200
    token = r.json()
    assert token["token_type"] == "bearer" and token["expires_in"] > 0
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token['access_token']}"})
    assert me.status_code == 200 and me.json()["email"] == "new.vendor@example.com"


def test_login_email_is_case_insensitive(client, vendor_user):
    assert login(client, vendor_user.email.upper()).status_code == 200


def test_login_failures_share_one_message(client, vendor_user, make_user):
    inactive = make_user(active=False)
    responses = [
        login(client, vendor_user.email, "Wr0ngpassword"),
        login(client, "nobody@nowhere.in"),
        login(client, inactive.email),
    ]
    for r in responses:
        assert r.status_code == 401
        assert r.headers["WWW-Authenticate"] == "Bearer"
        # RFC 6749 token-endpoint error shape, which Swagger's Authorize box can display
        assert r.json()["error"] == "invalid_grant"
        assert r.json()["error_description"] == "Incorrect email or password"


def test_me_requires_token(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "not_authenticated"


def test_garbage_token_rejected(client):
    r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401


def test_token_for_deleted_user_rejected(client):
    token, _ = create_access_token("00000000-0000-0000-0000-000000000000", "ADMIN")
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_deactivation_revokes_existing_token_immediately(client, vendor_user, admin_user):
    headers = auth(vendor_user)
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    r = client.patch(f"/api/v1/users/{vendor_user.id}", json={"is_active": False}, headers=auth(admin_user))
    assert r.status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_role_in_token_is_not_trusted(client, vendor_user):
    """A token claiming ADMIN for a vendor account still gets vendor permissions."""
    token, _ = create_access_token(str(vendor_user.id), "ADMIN")
    r = client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
