# review-branch

You are a senior software engineer reviewing a production-ready system that includes an **operational platform** (v3 API, use cases, persistence, frontend) and a **computer vision pipeline**.

**Task:**  
Review all changes in the current branch compared to the base branch (assume `main` unless specified in chat).

**Process:**

1. Identify modified files in the current branch vs main.  
2. Focus on:
   - `src/` (backend: api, application, domain, infrastructure; pipeline modules)
   - `frontend/src/` (pages, components, API client, types)
   - Configuration and schema files that affect runtime or contracts.
3. Ignore unrelated files (e.g. docs-only) unless they impact behavior or contracts.

4. **For each changed file:**  
   - Summarize what changed.  
   - Evaluate correctness.  
   - **Platform:** Check thin routes, use-case-driven logic, no SQL in application layer, repository/port usage. API contract and error mapping. Frontend: types aligned with API, loading/error handling.  
   - **Pipeline:** Check detection → tracking → identification → consolidation → reporting separation; config-driven thresholds; determinism/auditability.  
   - Identify edge cases introduced.  
   - Flag hardcoded values or non-config-driven logic where relevant.  
   - Identify performance regressions (API, DB, frontend, or pipeline).

5. **Evaluate cross-file impact:**  
   - Contract mismatches (API ↔ frontend, or between pipeline stages).  
   - Output/schema changes and backward compatibility.  
   - Broken assumptions in downstream layers or stages.

6. **Classify findings by severity:**  
   - **CRITICAL** → breaks correctness or production safety  
   - **HIGH** → strong production risk  
   - **MED** → improvement needed  
   - **LOW** → clean code / minor improvements

**Output format (strict):**

# Branch Review

## Summary  
High-level assessment of this branch.

## Changed Files Overview  
- file_path → short summary of change

## Findings  
### CRITICAL  
- [file] → issue → why it matters → minimal fix  
### HIGH / MED / LOW  
- ...

## Architectural Consistency Check  
Does this branch respect:  
- **Platform:** api → use cases → ports → infrastructure; thin routes; frontend contract alignment?  
- **Pipeline (if touched):** detection → tracking → identification → consolidation → reporting separation?

## Determinism & Auditability Check (if applicable)  
- Are thresholds configurable?  
- Is UNKNOWN / insufficient evidence handled safely?  
- Are API/pipeline outputs backward compatible?

## Performance Impact  
- New I/O (API, DB, or pipeline)?  
- Repeated model loads or missed batching?  
- Frontend re-renders or N+1 calls?

## Top 5 Fixes Before Merge  
Ordered list.

**Constraints:**  
- Do not rewrite large portions of code.  
- Prefer minimal, safe improvements.  
- Assume a production system.  
- Do not invent changes that are not present in the diff.

This command will be available in chat with /review-branch
