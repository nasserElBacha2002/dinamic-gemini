#!/usr/bin/env bash
# Thin wrappers documented in recovery-policy.md
# Prefer: python -m scripts.ops.* from repo root with PYTHONPATH=backend
echo "Use: python -m scripts.ops.audit_job_state_consistency --dry-run"
echo "Use: python -m scripts.ops.inspect_job --job-id <id>"
echo "Use: python -m scripts.ops.recover_job --job-id <id> --dry-run --actor <ops> --reason '<why>'"
