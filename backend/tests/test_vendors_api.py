import uuid

from app.services import vendor_service
from tests.conftest import auth


def create(client, payload, user):
    return client.post("/api/v1/vendors", json=payload, headers=auth(user))


def move(client, vid, target, user, reason="test"):
    return client.post(f"/api/v1/vendors/{vid}/status", json={"to_status": target, "reason": reason},
                       headers=auth(user))


def test_health_is_public(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/health/ready").json()["database"] == "up"


def test_vendor_endpoints_require_login(client, vendor_payload):
    assert client.post("/api/v1/vendors", json=vendor_payload).status_code == 401
    assert client.get("/api/v1/vendors").status_code == 401
    assert client.get(f"/api/v1/vendors/{uuid.uuid4()}").status_code == 401


def test_unknown_route_uses_error_envelope(client):
    r = client.get("/api/v1/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


# ---------- registration ----------

def test_register_vendor_sets_owner_and_normalizes(client, vendor_payload, vendor_user):
    r = create(client, vendor_payload, vendor_user)
    assert r.status_code == 201
    body = r.json()
    assert body["owner_id"] == str(vendor_user.id)
    assert body["status"] == "PENDING"
    assert body["email"] == "ops@medisupply.in" and body["gstin"] == "27AAPFU0939F1ZV"
    assert body["legal_name"] == "MediSupply Pvt Ltd"
    assert (body["region"], body["service_type"]) == ("west", "medical_equipment")
    assert "X-Request-ID" in r.headers


def test_only_vendor_role_registers_applications(client, vendor_payload, ops_user, admin_user):
    for user in (ops_user, admin_user):
        assert create(client, vendor_payload, user).status_code == 403


def test_one_application_per_account(client, vendor_payload, other_vendor_payload, vendor_user):
    create(client, vendor_payload, vendor_user)
    r = create(client, other_vendor_payload, vendor_user)
    assert r.status_code == 409 and r.json()["error"]["code"] == "vendor_profile_exists"


def test_duplicate_email_across_accounts(client, vendor_payload, vendor_user, other_vendor_user):
    create(client, vendor_payload, vendor_user)
    r = create(client, {**vendor_payload, "email": "OPS@medisupply.IN", "gstin": "29AABCU9603R1ZM"},
               other_vendor_user)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "duplicate_vendor"
    assert r.json()["error"]["details"]["fields"] == ["email"]


def test_duplicate_gstin_across_accounts(client, vendor_payload, vendor_user, other_vendor_user):
    create(client, vendor_payload, vendor_user)
    r = create(client, {**vendor_payload, "email": "other@vendor.in"}, other_vendor_user)
    assert r.status_code == 409 and r.json()["error"]["details"]["fields"] == ["gstin"]


def test_database_constraint_catches_race(client, vendor_payload, vendor_user, other_vendor_user,
                                          admin_user, monkeypatch):
    """Simulates two concurrent requests that both pass the application-level check."""
    create(client, vendor_payload, vendor_user)
    monkeypatch.setattr(vendor_service, "find_duplicate_fields", lambda *a, **k: [])
    r = create(client, vendor_payload, other_vendor_user)
    assert r.status_code == 409 and r.json()["error"]["code"] == "duplicate_vendor"
    assert client.get("/api/v1/vendors", headers=auth(admin_user)).json()["total"] == 1


def test_invalid_gstin_returns_422(client, vendor_payload, vendor_user):
    r = create(client, {**vendor_payload, "gstin": "NOTAGSTIN"}, vendor_user)
    assert r.status_code == 422
    assert r.json()["error"]["details"]["errors"][0]["field"] == "gstin"


# ---------- visibility ----------

def test_vendor_sees_only_own_application(client, vendor_payload, other_vendor_payload,
                                          vendor_user, other_vendor_user, ops_user):
    mine = create(client, vendor_payload, vendor_user).json()["id"]
    theirs = create(client, other_vendor_payload, other_vendor_user).json()["id"]

    listed = client.get("/api/v1/vendors", headers=auth(vendor_user)).json()
    assert listed["total"] == 1 and listed["items"][0]["id"] == mine

    # 404, not 403: a vendor cannot even learn that another application exists.
    r = client.get(f"/api/v1/vendors/{theirs}", headers=auth(vendor_user))
    assert r.status_code == 404
    assert move(client, theirs, "REJECTED", vendor_user).status_code == 404

    assert client.get("/api/v1/vendors", headers=auth(ops_user)).json()["total"] == 2


def test_my_vendor_endpoint(client, vendor_payload, vendor_user):
    assert client.get("/api/v1/vendors/me", headers=auth(vendor_user)).status_code == 404
    vid = create(client, vendor_payload, vendor_user).json()["id"]
    assert client.get("/api/v1/vendors/me", headers=auth(vendor_user)).json()["id"] == vid


def test_staff_filters(client, vendor_payload, other_vendor_payload, vendor_user, other_vendor_user, ops_user):
    create(client, vendor_payload, vendor_user)
    create(client, other_vendor_payload, other_vendor_user)
    south = client.get("/api/v1/vendors", params={"region": "South"}, headers=auth(ops_user)).json()
    assert south["total"] == 1 and south["items"][0]["region"] == "south"
    assert client.get("/api/v1/vendors", params={"status": "APPROVED"}, headers=auth(ops_user)).json()["total"] == 0
    assert len(client.get("/api/v1/vendors", params={"limit": 1}, headers=auth(ops_user)).json()["items"]) == 1


# ---------- status changes ----------

def test_vendors_cannot_change_status_directly(client, vendor_payload, vendor_user):
    """Uploading documents moves the application; vendors never set status by hand."""
    vid = create(client, vendor_payload, vendor_user).json()["id"]
    for target in ("APPROVED", "DOCUMENTS_SUBMITTED"):
        r = move(client, vid, target, vendor_user)
        assert r.status_code == 403  # role check happens before the state machine
        assert r.json()["error"]["details"]["allowed_targets"] == []


def test_full_review_flow_with_audit_actors(client, vendor_payload, vendor_user, ops_user, admin_user):
    vid = create(client, vendor_payload, vendor_user).json()["id"]
    for target in ["DOCUMENTS_SUBMITTED", "UNDER_REVIEW", "MANUAL_REVIEW", "APPROVED"]:
        r = move(client, vid, target, ops_user)
        assert r.status_code == 200 and r.json()["status"] == target

    logs = client.get(f"/api/v1/vendors/{vid}/audit-logs", headers=auth(admin_user)).json()
    assert [log["action"] for log in logs] == ["vendor_created"] + ["status_changed"] * 4
    assert logs[0]["actor"] == f"user:{vendor_user.id}"
    assert all(log["actor"] == f"user:{ops_user.id}" for log in logs[1:])
    assert logs[-1]["details"] == {"from": "MANUAL_REVIEW", "to": "APPROVED", "reason": "test", "role": "OPERATIONS"}
    assert all(log["request_id"] for log in logs)


def test_invalid_transition_returns_409(client, vendor_payload, vendor_user, ops_user):
    vid = create(client, vendor_payload, vendor_user).json()["id"]
    r = move(client, vid, "APPROVED", ops_user)
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "invalid_state_transition"
    assert err["details"]["allowed"] == ["DOCUMENTS_SUBMITTED", "REJECTED"]
    assert client.get(f"/api/v1/vendors/{vid}", headers=auth(ops_user)).json()["status"] == "PENDING"


def test_vendors_cannot_read_audit_logs(client, vendor_payload, vendor_user):
    vid = create(client, vendor_payload, vendor_user).json()["id"]
    assert client.get(f"/api/v1/vendors/{vid}/audit-logs", headers=auth(vendor_user)).status_code == 403
