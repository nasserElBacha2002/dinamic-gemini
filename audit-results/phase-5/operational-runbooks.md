# Phase 5 — Operational runbooks

## 1. API not ready

**Symptoms:** `/ready` 503; deploy unhealthy.  
**Alerts:** api_not_ready, http_5xx_rate.  
**Diagnose:** curl `/ready`; check schema_guard; repository backend reason.  
**Safe:** restart API; verify SQL; roll back release.  
**Validate:** `/ready` 200; `/health` ok.

## 2. SQL down

**Symptoms:** ready REPOSITORY_BACKEND_UNAVAILABLE; connection failures.  
**Alerts:** sql_unavailable.  
**Diagnose:** SQL connectivity; pool; recent migrations.  
**Safe:** failover / restore connectivity; do not enable MEMORY_ONLY in hosted.  
**Validate:** ready 200; sample job list.

## 3. Worker down

**Symptoms:** queue growth; no heartbeat.  
**Alerts:** worker_no_heartbeat, queue_depth_*.  
**Diagnose:** process supervisor; worker logs; lease table.  
**Safe:** restart worker; scale replicas.  
**Validate:** heartbeat gauge; pending drain.

## 4. Jobs stale

**Symptoms:** RUNNING with expired lease; STALE_JOB failures.  
**Alerts:** job_stuck.  
**Diagnose:** `inspect_job`; consistency audit.  
**Safe:** allow stale-fail reclaim; create retry via product retry if needed.  
**Destructive:** never steal lease without ADR.  
**Validate:** no expired RUNNING; aisle consistent.

## 5. Queue growing

**Symptoms:** pending depth rising.  
**Alerts:** queue_depth_high/critical.  
**Diagnose:** worker capacity; provider outages; claim errors.  
**Safe:** scale workers; pause non-critical tenants.  
**Validate:** depth trend down.

## 6. Lease loss elevated

**Symptoms:** high `job_lease_lost_total` / stale writes.  
**Alerts:** lease_loss_elevated, stale_write_rate.  
**Diagnose:** clock skew; overlapping workers; heartbeat interval.  
**Safe:** reduce concurrency; check fencing.  
**Validate:** rates normalize.

## 7. Artifact outbox blocked

**Symptoms:** pending/failed outbox growth.  
**Alerts:** outbox_blocked.  
**Diagnose:** storage credentials; `debug_artifact_publication.py`.  
**Safe:** fix storage; republish via admin dry-run then confirm.  
**Validate:** pending decreases.

## 8. Provider rate limit

**Symptoms:** 429 / PROVIDER_RATE_LIMIT.  
**Alerts:** provider_degraded.  
**Diagnose:** provider dashboards; retry metrics.  
**Safe:** backoff; reduce concurrency; switch provider if configured.  
**Validate:** error ratio down.

## 9. Uploads failing

**Symptoms:** upload_rejected / client errors.  
**Alerts:** upload_failures.  
**Diagnose:** MIME/size limits; auth; storage.  
**Safe:** adjust limits carefully; fix client.  
**Validate:** success rate recovers.

## 10. Operational job inconsistent

**Symptoms:** operational_job_id not SUCCEEDED; aisle PROCESSING with terminal job.  
**Alerts:** operational_job_inconsistent.  
**Diagnose:** consistency audit; admin finalization recovery dry-run.  
**Safe:** reconcile via admin tools.  
**Validate:** aisle/job SoT aligned.

## 11. Manual recovery

**Commands:** see `recovery-policy.md`.  
**Always:** dry-run first; actor+reason; refuse active lease.

## 12. Rollback release

**Symptoms:** elevated 5xx / ready failures after deploy.  
**Safe:** redeploy previous image; verify ready; drain queue.  
**Validate:** SLIs recover; no Phase 6 changes required.
