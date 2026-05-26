# GCP service account credentials (local / Docker)

Container path (see `.env`):

```txt
/app/secrets/gcp-service-account.json
```

Host paths (this repo — use **one**):

```txt
secrets/gcp-service-account.json              # default (repo root)
backend/secrets/gcp-service-account.json     # optional; use docker-compose.override.yml
```

## Setup

1. In [Google Cloud Console](https://console.cloud.google.com/) → IAM → Service Accounts, create or select a service account with access to your artifact bucket (e.g. `roles/storage.objectAdmin` on the bucket).
2. Create a JSON key and download it.
3. Save it as **`secrets/gcp-service-account.json`** at the repo root (recommended), **or** **`backend/secrets/gcp-service-account.json`** on the DEV server with `backend/docker-compose.override.yml` (see `backend/docker-compose.override.example.yml`).
4. **`backend/docker-compose.yml`** mounts repo-root secrets: `../secrets:/app/secrets:ro`.
5. On deploy, `backend/scripts/check_deploy_secrets.sh` verifies the file exists on the host and inside the container before migrations.

**Never commit** the real JSON. Only `gcp-service-account.json.example` is tracked.

## Local backend (without Docker)

Point `.env` at the host file instead:

```env
GOOGLE_APPLICATION_CREDENTIALS=secrets/gcp-service-account.json
```

(use a path relative to the repo root, or an absolute path on your machine)
