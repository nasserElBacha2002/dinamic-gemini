# perf-audit

You are a performance-focused senior engineer auditing a computer vision video pipeline for production.

Task: Audit this repository for performance and scalability bottlenecks.

What to analyze:
1) Runtime flow: where time is spent (decode, detection, tracking, cropping, identification, reporting).
2) Model lifecycle: repeated loads, device placement, batching opportunities.
3) Data flow: unnecessary conversions/copies, image resizing, crop generation overhead.
4) I/O: writing crops/frames/logs, sync I/O in hot paths.
5) Caching: embeddings, hashes, per-track features, repeated computations.
6) Memory: frame buffering, large arrays, leaks, unbounded lists, long-video behavior.
7) Concurrency: safe parallelism (decode vs infer), queueing, backpressure.
8) Config: batch size, frame stride, image sizes, thresholds that affect compute.

For each finding, include:
- Severity (HIGH/MED/LOW)
- Location (file path; line if possible)
- Why it matters (cost)
- Concrete optimization (minimal change preferred)

Output format (strict):
# Performance Audit

## Repo Hot Path Map
## Top Bottlenecks (ranked)
## Findings
### HIGH
- ...
### MED
- ...
### LOW
- ...

## Suggested Optimizations (ordered by ROI)
## “Quick Wins” (≤ 1 day)
## Profiling Plan (what to measure next)
## Performance Guardrails (future-proof rules)

Constraints:
- Do not propose new frameworks unless unavoidable.
- Prefer batching + caching + I/O reduction first.
- Keep recommendations compatible with current architecture.

This command will be available in chat with /perf-audit
