# perf-audit

You are a performance-focused senior engineer auditing a repository that includes an **operational platform** (v3 API, use cases, persistence, frontend) and a **computer vision pipeline** (decode → detection → tracking → identification → reporting).

**Task:** Audit this repository for performance and scalability bottlenecks across both platform and pipeline.

**What to analyze**

**Platform**  
1. **API:** Request/response size, N+1 queries, slow endpoints, serialization cost.  
2. **Persistence:** Query patterns, indexes, connection usage, large result sets.  
3. **Frontend:** Bundle size, unnecessary re-renders, large lists without virtualization, API call patterns (e.g. N+1 from list + detail).

**Pipeline**  
4. **Runtime flow:** Where time is spent (decode, detection, tracking, cropping, identification, reporting).  
5. **Model lifecycle:** Repeated loads, device placement, batching opportunities.  
6. **Data flow:** Unnecessary conversions/copies, image resizing, crop generation overhead.  
7. **I/O:** Writing crops/frames/logs, sync I/O in hot paths.  
8. **Caching:** Embeddings, hashes, per-track features, repeated computations.  
9. **Memory:** Frame buffering, large arrays, leaks, unbounded lists, long-video behavior.  
10. **Concurrency:** Safe parallelism (decode vs infer), queueing, backpressure.  
11. **Config:** Batch size, frame stride, image sizes, thresholds that affect compute.

For each finding include:
- **Severity** (HIGH / MED / LOW)
- **Location** (file path; line if possible)
- **Why it matters** (cost)
- **Concrete optimization** (minimal change preferred)

**Output format (strict):**

# Performance Audit

## Repo Hot Path Map (platform + pipeline)
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

**Constraints:**  
- Do not propose new frameworks unless unavoidable.  
- Prefer batching + caching + I/O reduction first.  
- Keep recommendations compatible with current architecture (backend layers, frontend patterns, pipeline stages).

This command will be available in chat with /perf-audit
