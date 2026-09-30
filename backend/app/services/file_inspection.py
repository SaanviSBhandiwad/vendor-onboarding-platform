"""Decide what a file really is from its bytes, never from the client's filename or header."""

from dataclasses import dataclass

from fastapi import UploadFile

from app.core.exceptions import EmptyFileError, FileTooLargeError, UnsupportedFileTypeError


@dataclass(frozen=True)
class FileKind:
    content_type: str
    extension: str


_SIGNATURES: list[tuple[bytes, FileKind]] = [
    (b"%PDF-", FileKind("application/pdf", ".pdf")),
    (b"\x89PNG\r\n\x1a\n", FileKind("image/png", ".png")),
    (b"\xff\xd8\xff", FileKind("image/jpeg", ".jpg")),
]

ALLOWED_TYPES = sorted(kind.content_type for _, kind in _SIGNATURES)
_CHUNK = 1024 * 1024


def detect_kind(data: bytes) -> FileKind:
    for signature, kind in _SIGNATURES:
        if data.startswith(signature):
            return kind
    raise UnsupportedFileTypeError(
        "Only PDF, PNG and JPEG files are accepted", details={"allowed_types": ALLOWED_TYPES}
    )


def read_limited(upload: UploadFile, max_bytes: int) -> bytes:
    """Read in chunks and stop as soon as the limit is passed (Content-Length can lie)."""
    buf = bytearray()
    while chunk := upload.file.read(_CHUNK):
        buf += chunk
        if len(buf) > max_bytes:
            raise FileTooLargeError(
                f"File exceeds the {max_bytes // (1024 * 1024)} MB limit", details={"max_bytes": max_bytes}
            )
    if not buf:
        raise EmptyFileError("The uploaded file is empty")
    return bytes(buf)


def safe_display_name(filename: str | None, fallback: str) -> str:
    """Keep only the base name, for display and download. Storage never uses it."""
    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    name = "".join(ch for ch in name if ch.isprintable())
    return (name or fallback)[:255]
