FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# ALB → container HTTP: trust proxy headers so redirects and absolute URLs use the client TLS scheme (https).
ENV FORWARDED_TRUSTED_HOSTS=*

# System deps:
# - unixODBC + Microsoft ODBC Driver 18 for SQL Server (pyodbc).
# - libzbar0 for QR/barcode scan (pyzbar): sync aisle code scan API here, and Phase 3 CODE_SCAN
#   worker path in Dockerfile.worker (both images install libzbar0).
# - tesseract-ocr (+ spa/eng) for Phase 4 INTERNAL_OCR: OpenCloud DEV spawns on-demand workers
#   inside this API container (docker-compose only runs `api`), so the binary must live here too.
# - Use Microsoft's Debian 12 repo WITHOUT [arch=amd64] so apt installs the native .deb (amd64 or arm64).
#   The previous amd64-only apt line broke ARM64 images: libc6:amd64 is not installable on aarch64.
RUN apt-get update && apt-get install -y --no-install-recommends \
    apt-transport-https \
    build-essential \
    ca-certificates \
    curl \
    git \
    gnupg \
    libglib2.0-0 \
    libgssapi-krb5-2 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libxcb1 \
    libgl1 \
    libzbar0 \
    tesseract-ocr \
    tesseract-ocr-spa \
    tesseract-ocr-eng \
    unixodbc \
    unixodbc-dev \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /etc/apt/keyrings/microsoft.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/microsoft.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/microsoft-prod.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && echo "msodbcsql18 image arch audit: $(dpkg --print-architecture)" \
    && dpkg -s msodbcsql18 | grep -E '^Package:|^Version:|^Architecture:' \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    python - <<'PY'
import pyodbc

drivers = {d.strip() for d in pyodbc.drivers() if d.strip()}
required = {"ODBC Driver 18 for SQL Server"}
print("pyodbc OK; ODBC drivers:", sorted(drivers))
if not (drivers & required):
    raise SystemExit(
        "Build verification failed: ODBC Driver 18 for SQL Server not registered. "
        f"Got: {sorted(drivers)}"
    )
from pyzbar.pyzbar import decode as _pyzbar_decode
print("pyzbar-ok")

# Phase 4 INTERNAL_OCR: OpenCloud on-demand workers run in this API image.
import pytesseract
_ver = str(pytesseract.get_tesseract_version())
print(f"pytesseract OK; tesseract version={_ver}")
_langs = {x.strip() for x in pytesseract.get_languages(config="") if x.strip()}
if "spa" not in _langs or "eng" not in _langs:
    raise SystemExit(
        f"Build verification failed: tesseract requires spa+eng. Got: {sorted(_langs)}"
    )
if not ({"spa", "eng"} <= _langs):
    raise SystemExit(
        f"Build verification failed: tesseract languages must include spa and eng. Got: {sorted(_langs)}"
    )
print("tesseract spa+eng language packs available for INTERNAL_OCR")
# Negative probe at runtime (missing binary after image build) requires container restart —
# this image is immutable; do not add probe retries.
PY

COPY . .

EXPOSE 8000

CMD ["uvicorn", "src.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
