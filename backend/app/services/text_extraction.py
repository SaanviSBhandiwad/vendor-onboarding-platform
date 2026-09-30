"""Turn a stored document into plain text: PDF text layer, or OCR for images."""

import io
import shutil
from dataclasses import dataclass

from PIL import Image
from pypdf import PdfReader

# Decompression-bomb guard: Pillow raises for images above twice this many pixels.
Image.MAX_IMAGE_PIXELS = 40_000_000
OCR_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class ExtractionResult:
    text: str
    page_count: int
    method: str
    needs_ocr: bool


def _clean(text: str) -> str:
    # PostgreSQL text columns cannot store NUL bytes, which some PDFs contain.
    return text.replace("\x00", "").strip()


def ocr_available() -> bool:
    return shutil.which("tesseract") is not None


def _open_image(data: bytes) -> Image.Image:
    # verify() catches truncated/corrupt files; it invalidates the object, so reopen afterwards.
    with Image.open(io.BytesIO(data)) as probe:
        probe.verify()
    image = Image.open(io.BytesIO(data))
    image.load()
    return image


def _ocr(image: Image.Image) -> str:
    import pytesseract  # only needed where OCR actually runs

    # Grayscale improves Tesseract accuracy on colour scans; timeout bounds worker time.
    return _clean(pytesseract.image_to_string(image.convert("L"), timeout=OCR_TIMEOUT_SECONDS))


def extract_text(data: bytes, content_type: str) -> ExtractionResult:
    if content_type == "application/pdf":
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise ValueError("PDF is password-protected")
        pages = [_clean(page.extract_text() or "") for page in reader.pages]
        text = "\n\n".join(p for p in pages if p)
        # No text layer usually means a scanned PDF; OCR of PDF pages is a later addition.
        return ExtractionResult(text, len(pages), "pdf_text_layer", needs_ocr=not text)

    if content_type.startswith("image/"):
        with _open_image(data) as image:  # corrupt images fail here, so the job is marked FAILED
            if not ocr_available():
                # Degrade gracefully: keep the file, flag it, let a reviewer read it.
                return ExtractionResult("", 1, "none", needs_ocr=True)
            text = _ocr(image)
        return ExtractionResult(text, 1, "ocr_tesseract", needs_ocr=not text)

    raise ValueError(f"No extractor for {content_type}")
