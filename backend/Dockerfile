FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# ALB → container HTTP: trust proxy headers so redirects and absolute URLs use the client TLS scheme (https).
ENV FORWARDED_TRUSTED_HOSTS=*

# System deps:
# - unixODBC runtime/dev for pyodbc (SQL Server requires a driver at runtime; Microsoft msodbcsql18 is amd64-only
#   and is omitted so this image builds on ARM64. Install a supported driver in derived images if needed.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    curl \
    git \
    libglib2.0-0 \
    libgssapi-krb5-2 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libxcb1 \
    libgl1 \
    unixodbc \
    unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    python - <<'PY'
import pyodbc

_drivers = sorted({d.strip() for d in pyodbc.drivers() if d.strip()})
print("pyodbc import OK; ODBC drivers visible to pyodbc:", _drivers)
PY

COPY . .

EXPOSE 8000

CMD ["uvicorn", "src.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
