# Phase 7 — Security final report

| Tool | Status | Notes |
| ---- | ------ | ----- |
| pip_audit | PASS (precondition + audit) | |
| bandit | FINDINGS allowed | policy |
| gitleaks detect/git + Docker pin | PASS | |
| npm audit FE/mobile | FINDINGS allowed | |
| trivy | **NOT_AVAILABLE** locally | install before claiming full DoD |
| hadolint | **NOT_AVAILABLE** locally | install before claiming full DoD |

Secrets: `.env` excluded from Docker context; gitleaks allowlists-only config.
No expired security exceptions reopened.
