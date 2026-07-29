"""Central Quality Gate tool policy (Phase 0).

All required tools and their blocking rules live here. Callers must not
hardcode area/tool lists in multiple places.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Tuple


@dataclass(frozen=True)
class ToolGateRule:
    """Policy for one required tool entry in audit-status.json."""

    area: str
    tool: str
    label: str
    failed_metric_keys: Tuple[str, ...] = ()
    # When True, status=FINDINGS alone does not fail the gate (progressive
    # security / advisory tools). Invalidating / omitted / metric failures still fail.
    allow_findings: bool = False
    required: bool = True


# Explicit Phase 0 required-tool set. Findings vs structural failure is
# controlled by allow_findings + failed_metric_keys + status vocabulary.
REQUIRED_TOOL_RULES: Tuple[ToolGateRule, ...] = (
    # Backend — hard quality
    ToolGateRule(
        area="backend",
        tool="pytest",
        label="Backend pytest",
        failed_metric_keys=("failed", "errors"),
    ),
    ToolGateRule(
        area="backend",
        tool="ruff",
        label="Backend Ruff",
        failed_metric_keys=("issues", "errors"),
    ),
    ToolGateRule(
        area="backend",
        tool="mypy",
        label="Backend Mypy",
        failed_metric_keys=("errors",),
    ),
    # Backend — security / deps
    # Bandit: FINDINGS allowed for low/medium; blocking_high metric fails the gate.
    ToolGateRule(
        area="backend",
        tool="bandit",
        label="Bandit",
        failed_metric_keys=("blocking_high",),
        allow_findings=True,
    ),
    ToolGateRule(
        area="backend",
        tool="pip-audit",
        label="pip-audit",
        failed_metric_keys=("total",),
        allow_findings=False,
    ),
    ToolGateRule(
        area="backend",
        tool="gitleaks",
        label="Gitleaks",
        failed_metric_keys=("secrets",),
        allow_findings=False,
    ),
    # Frontend — hard quality
    ToolGateRule(
        area="frontend",
        tool="typecheck",
        label="Frontend typecheck",
        failed_metric_keys=("ts_errors",),
    ),
    ToolGateRule(
        area="frontend",
        tool="vitest",
        label="Frontend Vitest",
        failed_metric_keys=("failed_tests",),
    ),
    # Lint: errors block; warning-only FINDINGS are allowed (progressive).
    ToolGateRule(
        area="frontend",
        tool="eslint",
        label="Frontend ESLint",
        failed_metric_keys=("errors",),
        allow_findings=True,
    ),
    ToolGateRule(
        area="frontend",
        tool="npm_audit",
        label="npm audit frontend",
        failed_metric_keys=(),
        allow_findings=True,
    ),
    # Mobile — hard quality
    ToolGateRule(
        area="mobile",
        tool="typecheck",
        label="Mobile typecheck",
        failed_metric_keys=("ts_errors",),
    ),
    ToolGateRule(
        area="mobile",
        tool="jest",
        label="Mobile Jest",
        failed_metric_keys=("failed",),
    ),
    ToolGateRule(
        area="mobile",
        tool="eslint",
        label="Mobile lint",
        failed_metric_keys=("errors",),
        allow_findings=True,
    ),
    ToolGateRule(
        area="mobile",
        tool="npm_audit",
        label="npm audit mobile",
        failed_metric_keys=(),
        allow_findings=True,
    ),
)

REQUIRED_AREAS: FrozenSet[str] = frozenset({"backend", "frontend", "mobile"})


def rules_for_area(area: str) -> Tuple[ToolGateRule, ...]:
    return tuple(r for r in REQUIRED_TOOL_RULES if r.area == area)


def policy_summary() -> list[dict[str, object]]:
    """Serializable view for docs / tests."""
    return [
        {
            "area": r.area,
            "tool": r.tool,
            "label": r.label,
            "allow_findings": r.allow_findings,
            "failed_metric_keys": list(r.failed_metric_keys),
            "required": r.required,
        }
        for r in REQUIRED_TOOL_RULES
    ]
