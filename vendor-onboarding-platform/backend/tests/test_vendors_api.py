import uuid

from app.services import vendor_service


def create(client, payload):
    return client.post("/api/v1/vendors", json=payload)


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/health/ready").json()["database"] == "up"


def test_register_vendor_normalizes_fields(client, vendor_payload):
    r = create(client, vendor_payload)
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "PENDING"
    assert body["email"] == "ops@medisupply.in"
    assert body["gstin"] == "27AAPFU0939F1ZV"
    assert body["legal_name"] == "MediSupply Pvt Ltd"
    assert body["region"] == "west"
    assert body["service_type"] == "medical_equipment"
    assert "X-Request-ID" in r.headers


def test_duplicate_email_is_rejected_case_insensitively(client, vendor_payload):
    assert create(client, vendor_payload).status_code == 201
    dup = {**vendor_payload, "email": "OPS@medisupply.IN", "gstin": "29AABCU9603R1ZM"}
    r = create(client, dup)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "duplicate_vendor"
    assert r.json()["error"]["details"]["fields"] == ["email"]


def test_duplicate_gstin_is_rejected(client, vendor_payload):
    create(client, vendor_payload)
    r = create(client, {**vendor_payload, "email": "other@vendor.in"})
    assert r.status_code == 409
    assert r.json()["error"]["details"]["fields"] == ["gstin"]


def test_database_constraint_catches_race(client, vendor_payload, monkeypatch):
    """Simulates two concurrent requests that both pass the application-level check."""
    create(client, vendor_payload)
    monkeypatch.setattr(vendor_service, "find_duplicate_fields", lambda *a, **k: [])
    r = create(client, vendor_payload)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "duplicate_vendor"
    assert client.get("/api/v1/vendors").json()["total"] == 1


def test_invalid_gstin_returns_422(client, vendor_payload):
    r = create(client, {**vendor_payload, "gstin": "NOTAGSTIN"})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation_error"
    assert err["details"]["errors"][0]["field"] == "gstin"


def test_get_missing_vendor_returns_404(client):
    r = client.get(f"/api/v1/vendors/{uuid.uuid4()}")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_list_and_filter(client, vendor_payload):
    create(client, vendor_payload)
    create(client, {**vendor_payload, "email": "b@x.in", "gstin": "29AABCU9603R1ZM", "region": "South"})
    assert client.get("/api/v1/vendors").json()["total"] == 2
    south = client.get("/api/v1/vendors", params={"region": "south"}).json()
    assert south["total"] == 1 and south["items"][0]["region"] == "south"
    assert client.get("/api/v1/vendors", params={"status": "APPROVED"}).json()["total"] == 0
    assert client.get("/api/v1/vendors", params={"limit": 1}).json()["items"].__len__() == 1


def test_full_happy_path_with_audit_trail(client, vendor_payload):
    vid = create(client, vendor_payload).json()["id"]
    for target in ["DOCUMENTS_SUBMITTED", "UNDER_REVIEW", "MANUAL_REVIEW", "APPROVED"]:
        r = client.post(f"/api/v1/vendors/{vid}/status", json={"to_status": target, "reason": "test"})
        assert r.status_code == 200, r.json()
        assert r.json()["status"] == target

    logs = client.get(f"/api/v1/vendors/{vid}/audit-logs").json()
    assert [log["action"] for log in logs] == ["vendor_created"] + ["status_changed"] * 4
    assert logs[-1]["details"] == {"from": "MANUAL_REVIEW", "to": "APPROVED", "reason": "test"}
    assert all(log["request_id"] for log in logs)


def test_invalid_transition_returns_409(client, vendor_payload):
    vid = create(client, vendor_payload).json()["id"]
    r = client.post(f"/api/v1/vendors/{vid}/status", json={"to_status": "APPROVED"})
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "invalid_state_transition"
    assert err["details"]["allowed"] == ["DOCUMENTS_SUBMITTED", "REJECTED"]
    # state unchanged, nothing audited beyond creation
    assert client.get(f"/api/v1/vendors/{vid}").json()["status"] == "PENDING"
    assert len(client.get(f"/api/v1/vendors/{vid}/audit-logs").json()) == 1
