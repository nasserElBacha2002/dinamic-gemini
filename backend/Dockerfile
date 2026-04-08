FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# ALB → container HTTP: trust proxy headers so redirects and absolute URLs use the client TLS scheme (https).
ENV FORWARDED_TRUSTED_HOSTS=*

# System deps:
# - unixODBC + Microsoft ODBC Driver 18 for SQL Server (pyodbc).
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
PY

COPY . .

EXPOSE 8000

CMD ["uvicorn", "src.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
