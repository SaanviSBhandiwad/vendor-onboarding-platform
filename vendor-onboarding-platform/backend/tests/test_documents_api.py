import shutil

import pytest

from app.api.v1.documents import get_max_upload_bytes
from app.main import app
from app.models import Job, JobStatus, VendorDocument
from app.services import audit_service
from tests.conftest import auth
from tests.files import JPEG, PNG, make_pdf


@pytest.fixture
def vendor(client, vendor_user, vendor_payload):
    return client.post("/api/v1/vendors", json=vendor_payload, headers=auth(vendor_user)).json()


def upload(client, vendor_id, user, data=None, doc_type="GST_CERTIFICATE", filename="gst.pdf", ctype="application/pdf"):
    data = make_pdf() if data is None else data
    return client.post(
        f"/api/v1/vendors/{vendor_id}/documents",
        data={"document_type": doc_type},
        files={"file": (filename, data, ctype)},
        headers=auth(user),
    )


def stored_files(storage):
    return [p for p in storage.root.rglob("*") if p.is_file()] if storage.root.exists() else []


# ---------- upload ----------

def test_upload_returns_202_and_queues_job(client, vendor, vendor_user, queue, storage):
    data = make_pdf()
    r = upload(client, vendor["id"], vendor_user, data)
    assert r.status_code == 202
    doc, job = r.json()["document"], r.json()["job"]
    assert doc["status"] == "UPLOADED" and doc["content_type"] == "application/pdf"
    assert doc["size_bytes"] == len(data) and len(doc["sha256"]) == 64
    assert doc["original_filename"] == "gst.pdf"
    assert job["status"] == "QUEUED" and job["document_id"] == doc["id"] and job["attempts"] == 0
    assert [str(j) for j in queue.enqueued] == [job["id"]]
    [path] = stored_files(storage)
    assert path.read_bytes() == data and path.name == f"{doc['id']}.pdf"  # never the user's filename


def test_type_comes_from_bytes_not_from_the_client(client, vendor, vendor_user):
    r = upload(client, vendor["id"], vendor_user, PNG, filename="scan.pdf", ctype="application/pdf")
    assert r.status_code == 202 and r.json()["document"]["content_type"] == "image/png"


@pytest.mark.parametrize("data", [b"just some text", b"MZ\x90\x00 fake exe", b"<html>"])
def test_unsupported_files_rejected(client, vendor, vendor_user, storage, data):
    r = upload(client, vendor["id"], vendor_user, data, filename="evil.pdf")
    assert r.status_code == 415
    assert r.json()["error"]["code"] == "unsupported_file_type"
    assert stored_files(storage) == []


def test_empty_file_rejected(client, vendor, vendor_user):
    r = upload(client, vendor["id"], vendor_user, b"")
    assert r.status_code == 400 and r.json()["error"]["code"] == "empty_file"


def test_file_too_large_rejected(client, vendor, vendor_user, storage):
    app.dependency_overrides[get_max_upload_bytes] = lambda: 100
    r = upload(client, vendor["id"], vendor_user, make_pdf())
    assert r.status_code == 413 and r.json()["error"]["details"]["max_bytes"] == 100
    assert stored_files(storage) == []


def test_path_in_filename_is_stripped(client, vendor, vendor_user):
    r = upload(client, vendor["id"], vendor_user, filename="..\\..\\windows/system32/gst.pdf")
    assert r.json()["document"]["original_filename"] == "gst.pdf"


def test_same_file_twice_is_rejected(client, vendor, vendor_user, storage):
    upload(client, vendor["id"], vendor_user)
    r = upload(client, vendor["id"], vendor_user, doc_type="OTHER")
    assert r.status_code == 409 and r.json()["error"]["code"] == "duplicate_document"
    assert len(stored_files(storage)) == 1


def test_invalid_document_type(client, vendor, vendor_user):
    assert upload(client, vendor["id"], vendor_user, doc_type="PASSPORT").status_code == 422


# ---------- automatic status ----------

def test_required_documents_move_application_automatically(client, vendor, vendor_user, ops_user):
    vid = vendor["id"]
    upload(client, vid, vendor_user, make_pdf("GST"), "GST_CERTIFICATE")
    listing = client.get(f"/api/v1/vendors/{vid}/documents", headers=auth(vendor_user)).json()
    assert listing["missing_types"] == ["BUSINESS_LICENSE"]
    assert client.get(f"/api/v1/vendors/{vid}", headers=auth(vendor_user)).json()["status"] == "PENDING"

    upload(client, vid, vendor_user, make_pdf("Licence"), "BUSINESS_LICENSE", "licence.pdf")
    listing = client.get(f"/api/v1/vendors/{vid}/documents", headers=auth(vendor_user)).json()
    assert listing["missing_types"] == [] and len(listing["items"]) == 2
    assert client.get(f"/api/v1/vendors/{vid}", headers=auth(vendor_user)).json()["status"] == "DOCUMENTS_SUBMITTED"

    logs = client.get(f"/api/v1/vendors/{vid}/audit-logs", headers=auth(ops_user)).json()
    assert [entry["action"] for entry in logs] == [
        "vendor_created", "document_uploaded", "document_uploaded", "status_changed"
    ]
    assert logs[-1]["details"]["automatic"] is True


def test_extra_documents_allowed_after_submission(client, vendor, vendor_user):
    upload(client, vendor["id"], vendor_user, make_pdf("a"), "GST_CERTIFICATE")
    upload(client, vendor["id"], vendor_user, make_pdf("b"), "BUSINESS_LICENSE")
    assert upload(client, vendor["id"], vendor_user, make_pdf("c"), "OTHER").status_code == 202


def test_documents_locked_once_review_starts(client, vendor, vendor_user, ops_user, storage):
    upload(client, vendor["id"], vendor_user, make_pdf("a"), "GST_CERTIFICATE")
    upload(client, vendor["id"], vendor_user, make_pdf("b"), "BUSINESS_LICENSE")
    client.post(f"/api/v1/vendors/{vendor['id']}/status", json={"to_status": "UNDER_REVIEW"}, headers=auth(ops_user))
    r = upload(client, vendor["id"], vendor_user, make_pdf("late"), "OTHER")
    assert r.status_code == 409 and r.json()["error"]["code"] == "documents_locked"
    assert len(stored_files(storage)) == 2


# ---------- access control ----------

def test_other_vendors_see_nothing(client, vendor, vendor_user, other_vendor_user):
    r = upload(client, vendor["id"], vendor_user)
    doc_id, job_id = r.json()["document"]["id"], r.json()["job"]["id"]
    h = auth(other_vendor_user)
    assert upload(client, vendor["id"], other_vendor_user, make_pdf("x")).status_code == 404
    assert client.get(f"/api/v1/vendors/{vendor['id']}/documents", headers=h).status_code == 404
    assert client.get(f"/api/v1/documents/{doc_id}", headers=h).status_code == 404
    assert client.get(f"/api/v1/documents/{doc_id}/file", headers=h).status_code == 404
    assert client.get(f"/api/v1/jobs/{job_id}", headers=h).status_code == 404


def test_staff_can_download(client, vendor, vendor_user, ops_user):
    data = make_pdf()
    doc_id = upload(client, vendor["id"], vendor_user, data).json()["document"]["id"]
    r = client.get(f"/api/v1/documents/{doc_id}/file", headers=auth(ops_user))
    assert r.status_code == 200 and r.content == data
    assert r.headers["content-type"] == "application/pdf"
    assert 'filename="gst.pdf"' in r.headers["content-disposition"]


def test_job_list_is_staff_only(client, vendor, vendor_user, ops_user):
    upload(client, vendor["id"], vendor_user)
    assert client.get("/api/v1/jobs", headers=auth(vendor_user)).status_code == 403
    listed = client.get("/api/v1/jobs", params={"status": "QUEUED"}, headers=auth(ops_user)).json()
    assert listed["total"] == 1


# ---------- failure handling ----------

def test_queue_down_returns_503_and_marks_job_failed(client, vendor, vendor_user, db_session):
    def broken_queue(job_id):
        raise ConnectionError("redis unreachable")

    from app.services.queue import get_job_queue
    app.dependency_overrides[get_job_queue] = lambda: broken_queue
    r = upload(client, vendor["id"], vendor_user)
    assert r.status_code == 503 and r.json()["error"]["code"] == "service_unavailable"
    job = db_session.get(Job, __import__("uuid").UUID(r.json()["error"]["details"]["job_id"]))
    assert job.status == JobStatus.FAILED and "ConnectionError" in job.error
    assert db_session.query(VendorDocument).count() == 1  # the file itself is kept


def test_database_failure_removes_the_stored_file(client, vendor, vendor_user, storage, monkeypatch, db_session):
    def boom(*a, **k):
        raise RuntimeError("database went away")

    monkeypatch.setattr(audit_service, "record", boom)
    with pytest.raises(RuntimeError):
        upload(client, vendor["id"], vendor_user)
    assert stored_files(storage) == []  # no orphaned file
    assert db_session.query(VendorDocument).count() == 0


# ---------- end to end with an inline worker ----------

def test_upload_then_poll_job_until_done(client, vendor, vendor_user, inline_worker):
    r = upload(client, vendor["id"], vendor_user, make_pdf("GSTIN 27AAPFU0939F1ZV valid"))
    job_id, doc_id = r.json()["job"]["id"], r.json()["document"]["id"]
    job = client.get(f"/api/v1/jobs/{job_id}", headers=auth(vendor_user)).json()
    assert job["status"] == "SUCCEEDED" and job["attempts"] == 1
    assert job["result"] == {"page_count": 1, "characters": 27, "method": "pdf_text_layer", "needs_ocr": False}
    doc = client.get(f"/api/v1/documents/{doc_id}", headers=auth(vendor_user)).json()
    assert doc["status"] == "PROCESSED" and doc["page_count"] == 1 and doc["extracted_chars"] == 27


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed")
def test_jpeg_upload_is_ocrd(client, vendor, vendor_user, inline_worker):
    r = upload(client, vendor["id"], vendor_user, JPEG, filename="photo.jpg", ctype="image/jpeg")
    job = client.get(f"/api/v1/jobs/{r.json()['job']['id']}", headers=auth(vendor_user)).json()
    assert job["status"] == "SUCCEEDED"
    assert job["result"]["method"] == "ocr_tesseract" and job["result"]["characters"] > 0
