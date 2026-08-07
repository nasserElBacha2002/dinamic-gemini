# syntax=docker/dockerfile:1.4
FROM python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93

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

# Non-root user (uid/gid 10001) before COPY so --chown works without recursive chown of the tree.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/output \
    && chown appuser:appuser /app /app/output

COPY requirements.txt .
COPY docker/verify_api_runtime_deps.py /tmp/verify_api_runtime_deps.py

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && python /tmp/verify_api_runtime_deps.py \
    && rm -f /tmp/verify_api_runtime_deps.py

COPY --chown=appuser:appuser . .
USER appuser

EXPOSE 8000

# Liveness against the existing public /health endpoint (curl already installed for ODBC setup).
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS --connect-timeout 3 --max-time 5 http://127.0.0.1:8000/health || exit 1

CMD ["uvicorn", "src.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
