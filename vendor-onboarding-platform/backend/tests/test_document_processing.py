import hashlib
import shutil
import uuid

import pytest

from app.core.logging import request_id_ctx
from app.models import AuditLog, DocumentStatus, DocumentType, Job, JobStatus, JobType, Vendor, VendorDocument
from app.services import document_processing, text_extraction
from app.services.storage import LocalStorage
from app.services.text_extraction import _clean, extract_text
from tests.files import CORRUPT_PNG, JPEG, PNG, make_image, make_pdf


@pytest.fixture
def queued_job(db_session, storage, vendor_user):
    def _make(data: bytes = None, content_type: str = "application/pdf"):
        data = make_pdf("Business Licence No 12345") if data is None else data
        vendor = Vendor(
            legal_name="V", email=f"{uuid.uuid4().hex[:6]}@v.in",
            gstin=f"27AAPFU{uuid.uuid4().int % 10**4:04d}F1ZV",
            region="west", service_type="goods", owner_id=vendor_user.id,
        )
        db_session.add(vendor)
        db_session.flush()
        doc = VendorDocument(vendor_id=vendor.id, document_type=DocumentType.BUSINESS_LICENSE,
                             original_filename="l.pdf", content_type=content_type, size_bytes=len(data),
                             sha256=hashlib.sha256(data).hexdigest(), storage_key=f"t/{uuid.uuid4()}")
        db_session.add(doc)
        db_session.flush()
        storage.save(doc.storage_key, data)
        job = Job(job_type=JobType.DOCUMENT_PROCESSING, vendor_id=vendor.id, document_id=doc.id)
        db_session.add(job)
        db_session.commit()
        return job, doc
    return _make


def test_pdf_job_succeeds(db_session, storage, queued_job):
    job, doc = queued_job()
    document_processing.run_job(db_session, storage, job.id)
    assert job.status == JobStatus.SUCCEEDED and job.attempts == 1
    assert job.started_at and job.finished_at and job.error is None
    assert doc.status == DocumentStatus.PROCESSED
    assert "Business Licence No 12345" in doc.extracted_text and doc.page_count == 1
    audit = db_session.query(AuditLog).filter_by(action="document_processed").one()
    assert audit.actor == "system:document_worker"


def test_duplicate_delivery_is_a_no_op(db_session, storage, queued_job):
    job, _ = queued_job()
    document_processing.run_job(db_session, storage, job.id)
    document_processing.run_job(db_session, storage, job.id)  # broker redelivers the same message
    assert job.attempts == 1
    assert db_session.query(AuditLog).filter_by(action="document_processed").count() == 1


def test_corrupt_pdf_marks_job_failed(db_session, storage, queued_job):
    job, doc = queued_job(b"%PDF-1.4\nthis is not really a pdf")
    document_processing.run_job(db_session, storage, job.id)
    assert job.status == JobStatus.FAILED and job.error and job.finished_at
    assert doc.status == DocumentStatus.FAILED
    assert db_session.query(AuditLog).filter_by(action="document_processing_failed").count() == 1


def test_tampered_file_fails_checksum(db_session, storage, queued_job):
    job, doc = queued_job()
    storage.save(doc.storage_key, make_pdf("tampered"))
    document_processing.run_job(db_session, storage, job.id)
    assert job.status == JobStatus.FAILED and "checksum" in job.error


def test_missing_file_fails_cleanly(db_session, storage, queued_job):
    job, doc = queued_job()
    storage.delete(doc.storage_key)
    document_processing.run_job(db_session, storage, job.id)
    assert job.status == JobStatus.FAILED and "FileNotFoundError" in job.error


def test_unknown_job_is_ignored(db_session, storage):
    document_processing.run_job(db_session, storage, uuid.uuid4())  # must not raise


needs_tesseract = pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed")


@needs_tesseract
@pytest.mark.parametrize(("data", "content_type"), [(PNG, "image/png"), (JPEG, "image/jpeg")])
def test_images_are_ocrd(data, content_type):
    result = extract_text(data, content_type)
    assert result.method == "ocr_tesseract" and not result.needs_ocr
    assert "BUSINESS LICENSE" in result.text


@needs_tesseract
def test_image_job_stores_ocr_text(db_session, storage, queued_job):
    job, doc = queued_job(make_image("GSTIN 27AAPFU0939F1ZV"), content_type="image/png")
    document_processing.run_job(db_session, storage, job.id)
    assert job.status == JobStatus.SUCCEEDED and job.result["method"] == "ocr_tesseract"
    # OCR is approximate (e.g. 0 read as O), so assert on words, not exact identifiers.
    # Downstream compliance checks must tolerate this.
    assert "GSTIN" in doc.extracted_text


def test_image_without_tesseract_is_flagged_not_failed(monkeypatch):
    monkeypatch.setattr(text_extraction, "ocr_available", lambda: False)
    result = extract_text(PNG, "image/png")
    assert result.needs_ocr and result.text == "" and result.method == "none"


def test_corrupt_image_fails_the_job(db_session, storage, queued_job):
    job, doc = queued_job(CORRUPT_PNG, content_type="image/png")
    document_processing.run_job(db_session, storage, job.id)
    assert job.status == JobStatus.FAILED and doc.status == DocumentStatus.FAILED
    assert job.error


def test_nul_bytes_removed():
    assert _clean("GST\x00IN ") == "GSTIN"


def test_storage_rejects_keys_outside_root(tmp_path):
    s = LocalStorage(tmp_path)
    with pytest.raises(ValueError):
        s.path("../../etc/passwd")


def test_celery_task_runs_job_and_carries_request_id(db_session, storage, queued_job, monkeypatch):
    from app.workers import tasks

    job, _ = queued_job()
    seen = {}
    real_run = document_processing.run_job

    def spy(db, st, job_id):
        seen["request_id"] = request_id_ctx.get()
        real_run(db_session, storage, job_id)

    class _Session:
        def __enter__(self):
            return db_session

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(tasks, "SessionLocal", _Session)
    monkeypatch.setattr(tasks.document_processing, "run_job", spy)
    tasks.process_document.apply(args=[str(job.id)], kwargs={"request_id": "req-123"})  # runs locally, no broker
    assert seen["request_id"] == "req-123"
    assert job.status == JobStatus.SUCCEEDED
    assert request_id_ctx.get() is None  # context restored afterwards
