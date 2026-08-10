# Phase 6 — Contract changes

## Internal (non-HTTP)

| Contract | Change | Compatibility |
| -------- | ------ | ------------- |
| `JobResultUnitOfWork.fence_job_lease` | Added to Protocol; returns `bool` | All UoW implementations updated; callers treat `False` as “caller must assert” |
| `MemoryJobResultUnitOfWork.job_repo` | Optional bind for assert | Production factory wires repo; tests may leave unbound |
| `DownloadCapacityExceededError` | Application error | API maps to 503 |
| `WorkerLaunchFailedError` | Typed recovery launch failure | Replaces string matching |

## HTTP / DB / mobile / frontend

No public API response shape changes. No migrations. No mobile/frontend contract changes.
