"""Tiny but valid test files, built in code so the repo needs no binary fixtures."""

import io

from PIL import Image, ImageDraw, ImageFont


def make_pdf(text: str = "GST Registration Certificate") -> bytes:
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % off for off in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


def make_image(text: str = "BUSINESS LICENSE", fmt: str = "PNG") -> bytes:
    """A real image with large dark text on white, readable by OCR."""
    image = Image.new("RGB", (900, 200), "white")
    ImageDraw.Draw(image).text((30, 60), text, fill="black", font=ImageFont.load_default(size=64))
    buf = io.BytesIO()
    image.save(buf, format=fmt)
    return buf.getvalue()


PNG = make_image()
JPEG = make_image(fmt="JPEG")
# Right signature, broken body: passes the upload type check, must fail in the worker.
CORRUPT_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
