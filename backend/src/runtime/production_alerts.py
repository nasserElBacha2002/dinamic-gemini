"""Phase 10 — catalog of production alert definitions (owner + action).

These are declarative contracts for ops dashboards / paging. Wiring to a
specific alerting backend (Prometheus, CloudWatch, etc.) is deployment-specific.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AlertSeverity = Literal["warning", "critical"]


@dataclass(frozen=True, slots=True)
class ProductionAlertDefinition:
    alert_id: str
    severity: AlertSeverity
    metric: str
    window: str
    owner: str
    action: str
    description: str


PRODUCTION_ALERT_CATALOG: tuple[ProductionAlertDefinition, ...] = (
    ProductionAlertDefinition(
        alert_id="queue_depth_high",
        severity="warning",
        metric="queue_depth",
        window="5m",
        owner="platform-ops",
        action="Scale workers; check claim/lease; pause non-critical tenants if critical.",
        description="Pending job queue depth above warning threshold.",
    ),
    ProductionAlertDefinition(
        alert_id="queue_depth_critical",
        severity="critical",
        metric="queue_depth",
        window="5m",
        owner="platform-ops",
        action="Page on-call; pause rollout; drain backlog before new tenants.",
        description="Pending job queue depth above critical threshold.",
    ),
    ProductionAlertDefinition(
        alert_id="oldest_pending_high",
        severity="warning",
        metric="oldest_pending_age",
        window="10m",
        owner="platform-ops",
        action="Inspect stuck jobs; reclaim expired leases; check provider health.",
        description="Oldest pending job age above warning threshold.",
    ),
    ProductionAlertDefinition(
        alert_id="job_stuck",
        severity="critical",
        metric="job_lease_expired_running",
        window="5m",
        owner="pipeline-oncall",
        action="Reclaim lease; inspect worker crash; verify heartbeat.",
        description="Job remains RUNNING past lease without heartbeat.",
    ),
    ProductionAlertDefinition(
        alert_id="worker_no_heartbeat",
        severity="critical",
        metric="worker_heartbeat_age",
        window="2m",
        owner="pipeline-oncall",
        action="Restart worker; check process supervisor; verify network to SQL.",
        description="Worker heartbeat missing beyond lease window.",
    ),
    ProductionAlertDefinition(
        alert_id="retry_rate_high",
        severity="warning",
        metric="retry_rate",
        window="15m",
        owner="pipeline-oncall",
        action="Check provider 429/5xx; inspect idempotency conflicts; throttle.",
        description="Excessive job retry rate.",
    ),
    ProductionAlertDefinition(
        alert_id="http_5xx_rate",
        severity="critical",
        metric="http_5xx_rate",
        window="5m",
        owner="api-oncall",
        action="Check API pods; SQL connectivity; circuit-break nonessential paths.",
        description="Elevated HTTP 5xx rate on v3 APIs.",
    ),
    ProductionAlertDefinition(
        alert_id="sql_connection_exhaustion",
        severity="critical",
        metric="sql_pool_wait",
        window="2m",
        owner="data-oncall",
        action="Raise pool carefully; kill long queries; pause workers if needed.",
        description="SQL connection pool near exhaustion.",
    ),
    ProductionAlertDefinition(
        alert_id="sql_deadlocks",
        severity="warning",
        metric="sql_deadlock_rate",
        window="15m",
        owner="data-oncall",
        action="Review transaction order; shorten critical sections; retry with backoff.",
        description="Deadlock rate above baseline.",
    ),
    ProductionAlertDefinition(
        alert_id="upload_failures",
        severity="warning",
        metric="upload_failure_rate",
        window="15m",
        owner="mobile-oncall",
        action="Check storage/auth; inspect MIME/size rejects; mobile connectivity.",
        description="Elevated mobile upload failure rate.",
    ),
    ProductionAlertDefinition(
        alert_id="finalization_failures",
        severity="critical",
        metric="finalization_failure_rate",
        window="15m",
        owner="pipeline-oncall",
        action="Check aisle locks; optimistic concurrency; rollback drill if needed.",
        description="Elevated aisle finalization failure rate.",
    ),
    ProductionAlertDefinition(
        alert_id="recovery_failures",
        severity="critical",
        metric="recovery_failure_rate",
        window="30m",
        owner="mobile-oncall",
        action="Inspect offline_operations leases; WorkManager; auth blocks.",
        description="Elevated offline / reboot recovery failure rate.",
    ),
)


def list_production_alerts(
    *, severity: AlertSeverity | None = None
) -> tuple[ProductionAlertDefinition, ...]:
    if severity is None:
        return PRODUCTION_ALERT_CATALOG
    return tuple(a for a in PRODUCTION_ALERT_CATALOG if a.severity == severity)
