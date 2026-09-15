# Final SAST results

| Tool | Executed | Exit / status | Disposition |
|------|----------|---------------|-------------|
| Bandit | Yes (`run_full_audit` + local) | FINDINGS allowed (no high in gate) | Triaged priority B608; residual medium noise accepted |
| pip-audit | Yes | OK | Clean / INFO-002 |
| Gitleaks (Docker via audit script) | Yes | EXECUTION_ERROR exit 126 | **Not PASS** — tooling invalid (OPS-001) |
| Gitleaks (host `--no-git`) | Yes | Reported 5 leaks | **NOT_VERIFIABLE** until paths classified (fixtures vs secrets) |
| Semgrep | Attempted | PermissionError on `~/.semgrep/semgrep.log` in sandbox | **NOT_VERIFIABLE** this session |
| npm audit frontend | Yes | moderate (vitest) | RISK_ACCEPTED SEC-007 |
| npm audit mobile | Yes | high/critical advisories | RISK_ACCEPTED SEC-006 via exceptions file |
| Trivy/OSV | Not configured in local command set | — | NOT_VERIFIABLE |

**Rule applied:** tools that failed to execute are not marked PASS_WITH_WARNINGS.

Evidence logs: `audit/remediation-final/tool-logs/` and `final-quality-gate-results.txt`.
