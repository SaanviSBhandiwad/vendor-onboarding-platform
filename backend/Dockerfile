FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UPLOAD_DIR=/data/uploads
WORKDIR /app

# Tesseract for OCR of image documents (the worker uses it; the API image shares the same build).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# The upload directory must exist and belong to appuser *in the image*: Docker copies
# this ownership into the named volume the first time it is mounted.
RUN useradd --create-home appuser \
    && mkdir -p /data/uploads && chown appuser:appuser /data/uploads \
    && chmod +x entrypoint.sh
USER appuser

EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
CMD ["api"]
