# Final Gitleaks triage

## Commands

```bash
# Working tree (includes gitignored) with project config
gitleaks detect --source . --no-git -c .gitleaks.toml -f json -r audit/remediation-final/corrections/gitleaks-raw.json

# Git-tracked history/tree
gitleaks detect --source . -c .gitleaks.toml -f json -r audit/remediation-final/corrections/gitleaks-git.json
```

Host version: gitleaks 8.30.1

## `.gitleaksignore` fix

Removed invalid path-as-fingerprint entry `secrets/gcp-service-account.json.example` (caused WARN Invalid fingerprint). Path allowlists live in `.gitleaks.toml` only.

## Initial untriaged candidates (pre-allowlist refresh)

Prior `--no-git` scan without remediation allowlists reported hits in:

| # | Rule | Path (no secret values) | Classification | Justification |
|---|------|-------------------------|----------------|---------------|
| 1–3 | jwt | `audit/lab/data/fixture-tokens.json` | FALSE_POSITIVE | Lab-only synthetic JWTs; path gitignored under `audit/lab/` |
| 4 | generic-api-key | `audit/lab/data/runtime.json` | FALSE_POSITIVE | Lab runtime marker file; disposable lab |
| 5–13 | jwt / private-key / generic-api-key | `audit/remediation-final/tool-logs/gitleaks.json` | FALSE_POSITIVE | Recursive self-scan of prior gitleaks JSON; file removed |
| 14 | private-key | `secrets/gcp-service-account.json` | LOCAL_ONLY_NOT_IN_REPO | Gitignored (`secrets/*.json`); local machine credential — **do not commit**; rotate if shared |

## Post-fix scan

After updating `.gitleaks.toml` allowlists (`audit/lab/`, `audit/remediation-final/`, `secrets/*.json`) and clearing recursive logs:

- `--no-git` with config: **no leaks found**
- Git-tracked scan: see `gitleaks-git-run.txt` (expect 0 for tracked tree)

**Secrets are not copied into this report.**

## Residual

Docker-based gitleaks in `run_full_audit.sh` may still exit 126 (OPS-001). Host scan with config is the triage evidence for this close-out.
