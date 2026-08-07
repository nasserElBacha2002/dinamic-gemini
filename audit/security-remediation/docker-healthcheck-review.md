# Docker HEALTHCHECK review

## Audit findings (LOW)

1. `backend/Dockerfile` — missing HEALTHCHECK  
2. `backend/Dockerfile.worker` — missing HEALTHCHECK  

## Orchestration inventory

| Surface | Healthcheck? |
|---------|--------------|
| `backend/docker-compose.yml` | No service-level `healthcheck:` block |
| `backend/docker-compose.override.example.yml` | No HEALTHCHECK duplication pattern |
| Kubernetes / Helm in-repo | Not present as product deployment source of truth |

Conclusion: health was **not** reliably defined at orchestrator layer for the API image → Dockerfile HEALTHCHECK is appropriate for the API.

## API image (`backend/Dockerfile`)

**Status: FIXED**

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS --connect-timeout 3 --max-time 5 http://127.0.0.1:8000/health || exit 1
```

Rationale:

- Uses existing public liveness endpoint `GET /health`.
- Uses **curl already installed** in the image (ODBC/Microsoft repo setup) — no extra package solely for healthcheck.
- Runs as non-root `appuser` after USER switch; curl to localhost is fine.

## Worker image (`backend/Dockerfile.worker`)

**Status: NOT_APPLICABLE**

- Worker CMD: `python -m src.jobs.run_worker` — **no HTTP listener**.
- Probing `/health` would be false confidence.
- No in-image process heartbeat protocol exposed for Docker HEALTHCHECK without inventing one.
- Comment added in Dockerfile documenting orchestrator/process supervision expectation.

Do **not** invent a fake HEALTHCHECK for scanner greenness.

## Residual

Compose-level healthchecks remain optional sugar; API image now self-describes liveness for Docker/Swarm-style probes.
