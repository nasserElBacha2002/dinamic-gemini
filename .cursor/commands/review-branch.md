# review-branch

You are a senior software engineer reviewing a production-ready computer vision inventory system.

Task:
Review all changes in the current branch compared to the base branch (assume "main" unless specified in chat).

Process:

1) Identify modified files in the current branch vs main.
2) Focus primarily on:
   - src/
   - pipeline-related modules
   - configuration files
3) Ignore unrelated files unless they impact runtime behavior.

4) For each changed file:
   - Summarize what changed.
   - Evaluate correctness.
   - Check architectural consistency.
   - Identify edge cases introduced.
   - Detect hardcoded values or non-config-driven logic.
   - Flag determinism or auditability risks.
   - Identify performance regressions.
   - Suggest minimal, incremental fixes.

5) Evaluate cross-file impact:
   - Contract mismatches between modules.
   - Output schema changes.
   - Broken assumptions in downstream stages.

6) Classify findings by severity:
   - CRITICAL → breaks correctness or production safety
   - HIGH → strong production risk
   - MED → improvement needed
   - LOW → clean code / minor improvements

Output format (strict):

# Branch Review

## Summary
High-level assessment of this branch.

## Changed Files Overview
- file_path → short summary of change

## Findings

### CRITICAL
- [file] → issue → why it matters → minimal fix

### HIGH
- ...

### MED
- ...

### LOW
- ...

## Architectural Consistency Check
Does this branch respect:
- detection → tracking → identification → consolidation → reporting separation?

## Determinism & Auditability Check
- Are thresholds configurable?
- Is UNKNOWN handled safely?
- Are outputs backward compatible?

## Performance Impact
- Any new I/O?
- Repeated model loads?
- Missed batching opportunities?

## Top 5 Fixes Before Merge
Ordered list.

Constraints:
- Do not rewrite large portions of code.
- Prefer minimal, safe improvements.
- Assume this is a production system.
- Do not invent changes that are not present in the diff.

This command will be available in chat with /review-branch
