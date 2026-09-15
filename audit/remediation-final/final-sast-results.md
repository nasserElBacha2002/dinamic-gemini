# Final SAST results (post-corrections)

| Tool | Command / notes | Exit | Disposition |
|------|-----------------|------|-------------|
| Bandit | Via `run_full_audit.sh` (when gate completes) | see gate log | Triaged B608 priority earlier |
| pip-audit | Via gate / prior | OK historically | INFO clean |
| Gitleaks host | `--no-git -c .gitleaks.toml` + git history | 0 leaks | TRIAGED — see `final-gitleaks-triage.md` |
| Gitleaks Docker (gate) | `run_full_audit.sh` | often 126 | BLOCKED tooling — not PASS |
| Semgrep registry `p/python` | Download via semgrep.dev | Proxy 403 | NOT_VERIFIABLE for registry |
| Semgrep local | `SEMGREP_LOG_FILE=... --config=corrections/semgrep-local.yaml` | 0 | EXECUTED_LOCAL_RULESET (1 rule) |
| npm audit FE | `npm audit --audit-level=high` | 0 (moderate only) | RISK_ACCEPTED SEC-007 |
| npm audit mobile | high/critical | non-zero | RISK_ACCEPTED SEC-006 |
| Trivy/OSV | — | — | NOT_RUN |

Failed/blocked tools are **not** marked PASS_WITH_WARNINGS.
