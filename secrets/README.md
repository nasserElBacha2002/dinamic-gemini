# GCP service account credentials (local / Docker)

Container path (see `.env`):

```txt
/app/secrets/gcp-service-account.json
```

Host path (this repo):

```txt
secrets/gcp-service-account.json
```

## Setup

1. In [Google Cloud Console](https://console.cloud.google.com/) → IAM → Service Accounts, create or select a service account with access to your artifact bucket (e.g. `roles/storage.objectAdmin` on the bucket).
2. Create a JSON key and download it.
3. Save it as **`secrets/gcp-service-account.json`** (replace the placeholder file).
4. Ensure `backend/docker-compose.yml` mounts this folder (already configured as `../secrets:/app/secrets:ro`).

**Never commit** the real JSON. Only `gcp-service-account.json.example` is tracked.

## Local backend (without Docker)

Point `.env` at the host file instead:

```env
GOOGLE_APPLICATION_CREDENTIALS=secrets/gcp-service-account.json
```

(use a path relative to the repo root, or an absolute path on your machine)
