# corrections-scoped

**ROLE**  
You are a senior engineer applying a scope-controlled corrective patch to a v3 inventory operations platform. The repo includes backend API, application use cases, persistence, frontend, and a CV/LLM processing pipeline.

**PRIMARY GOAL**  
Apply only the fixes explicitly listed by the user. Do not add features. Do not perform unrelated refactors. Do not change contracts unless the fix explicitly requires it.

This command is **stricter than** `/implement`: smaller blast radius, explicit fix list only, no stage implementation.

---

## 0. Audit / read-only guard (check first)

Before editing any file:

- If the user asks only for **audit**, **analysis**, **read-only review**, or **code review** — **do not edit files**.
- Produce a read-only report (findings, risks, recommended fixes) and stop.
- Do not run corrective patches in read-only mode.

If the user wants fixes applied, they must provide a concrete fix list (see below).

---

**USER FIX LIST**  
The user will provide the exact fixes in chat.  
If no fix list is provided, stop and ask:

“Please list the fixes to apply, including file/area and desired behavior.”

Set final status to `BLOCKED` until a fix list is provided.

---

**STRICT RULES** (do not weaken)

- Only touch files required by the listed fixes.
- Do not change unrelated code.
- Do not add features.
- Do not perform unrelated refactors.
- Do not rename public APIs unless explicitly required.
- Do not change API response shapes unless explicitly required.
- Do not change database schema unless explicitly required.
- Do not modify prompt behavior unless explicitly required.
- Do not add dependencies unless explicitly required.
- Do not add feature flags unless explicitly required.
- Do not rewrite entire files if a minimal patch is enough.
- Do not update snapshots blindly. First verify the intended behavior.
- Do not silence tests/lint errors without fixing the cause.
- Do not delete tests unless the user explicitly asks and explains why.
- If you discover a larger issue not in the fix list, report it as a **follow-up recommendation** — do **not** fix it without explicit user approval.

---

**PROCESS**

## 1. Understand the fix list

Before editing:

- Restate each requested fix.
- Identify whether it affects:
  - backend
  - frontend
  - persistence
  - pipeline
  - tests
  - config
  - docs

If a requested fix is ambiguous, choose the safest minimal interpretation and mention the assumption.

## 2. Inspect target files

Read the relevant files and identify:

- exact functions/classes/components to patch
- existing conventions
- related tests
- contracts that must be preserved

## 3. Minimal patch plan

Before editing, output:

- file-by-file plan
- exact behavior change
- tests to update/add
- validation commands

## 4. Apply changes

Rules:

- One concern per patch when possible.
- Keep changes minimal.
- Preserve backward compatibility.
- Preserve deterministic behavior.
- Keep routes thin.
- Keep business logic out of UI components where existing architecture separates it.
- Keep adapters/normalization responsibilities intact.
- Avoid broad formatting changes unless the repo formatter requires them.

## 5. Tests and validation

For each fix:

- Add or update tests when meaningful.
- Run targeted tests first.
- Run broader checks if the affected area requires it.
- If failures are unrelated, report them separately and do not hide them.

## 6. Working-tree inspection (staged vs unstaged)

Before the final response, inspect Git state. This is for **review only** — not for committing.

Rules:

- Do **not** stage real content (`git add` without `-N` is not allowed unless the user explicitly asked to stage).
- `git add -N .` is allowed only so **untracked** files appear in `git diff`.
- If **staged** changes already exist, mention them explicitly — do not hide pre-existing staged changes.
- The review package covers **uncommitted** working-tree changes; **distinguish staged from unstaged** in the output.

Run (from repository root):

```bash
git add -N .
git --no-pager status --short
git --no-pager diff --cached --name-status
git --no-pager diff --stat
git --no-pager diff --numstat
git --no-pager diff --name-status
```

Optional helper (same artifacts as `/implement`; correction-specific classification is still your responsibility in §7–8):

```bash
./scripts/review_working_tree.sh
```

Use `.review/` only as local, gitignored helpers — see §9.

## 7. Correction diff mode (CORRECTION_SMALL vs CORRECTION_LARGE)

Classify the patch for the **Review package** section:

### `CORRECTION_SMALL_DIFF`

Use when **all** are true:

- **1 to 8** changed files (from `git diff --name-status` after `git add -N .`), and
- total changed lines (insertions + deletions from `git diff --numstat`) **under ~600**, and
- changes are limited to the **explicitly listed fixes**, and
- tests changed only to validate those fixes.

**Do not** upgrade to large diff only because tests changed alongside the fix:

- `frontend/src/...` + `frontend/tests/...` → still **CORRECTION_SMALL_DIFF**
- `backend/src/...` + `backend/tests/...` → still **CORRECTION_SMALL_DIFF**

### `CORRECTION_LARGE_DIFF`

Use when **any** is true:

- more than **8** changed files, or
- more than **~600** total changed lines, or
- changes **unexpectedly** span multiple **unrelated** areas (not source + matching tests), or
- corrections required touching **backend + frontend + migrations/config/pipeline** together, or
- you had to modify **more files than the fix list implied**.

When in `CORRECTION_LARGE_DIFF`, **warn** that the correction may have exceeded intended scope (see **Scope control**).

Thresholds align with `scripts/review_working_tree.sh` (`MAX_SMALL_FILES=8`, `MAX_SMALL_LINES=600`) for line/file counts; correction mode uses **stricter scope** rules above for classification.

## 8. Scope control (required in final output)

Produce a **Scope control** section:

```md
## Scope control

Requested fixes:
- ...

Touched areas:
- ...

Scope drift:
- none
```

or:

```md
Scope drift:
- WARNING: <explanation>
```

Rules:

- If a file was modified but is not directly related to a requested fix → flag **WARNING**.
- If formatting-only changes touched unrelated lines → flag **WARNING**.
- If a test was updated because behavior changed intentionally → explain (not necessarily drift).
- Larger issues discovered but not requested → **follow-up recommendation only**; do not fix.

## 9. `.review/` and local artifact safety (hard rules)

- Review artifacts must **not** pollute Git status.
- After `git add -N .`, if `.review/` or `review-working-tree.txt` appears in `git status --short`:
  - ensure `.review/` is in `.gitignore` (acceptable for workflow-only updates), **or**
  - remove local review artifacts before finishing.
- **Never** list `.review/` files or `review-working-tree.txt` under **Files modified/created** unless the user explicitly asked to version them.
- Never commit `.review/`.

---

**FINAL STATUS RULES**

- **`CORRECTIONS_VALIDATED`** — All requested fixes applied; scope remained controlled; targeted validation passed; no unrelated failures caused by your patch.
- **`CORRECTIONS_WITH_WARNINGS`** — Requested fixes applied; warnings present (e.g. unrelated pre-existing failures, pre-existing staged changes, minor scope-risk, `CORRECTION_LARGE_DIFF` with controlled scope); no blocking validation failure **caused by** the corrections.
- **`BLOCKED`** — Fix list missing or ambiguous; required files/contracts cannot be safely changed; tests fail **due to** the correction; scope drift would be required to complete the fix; user confirmation needed.

---

**OUTPUT FORMAT**

Return these sections **in order**:

1. **Fixes applied**  
2. **Scope control** (§8)  
3. **Files modified/created** (production/source only — exclude `.review/`, `review-working-tree.txt`)  
4. **Behavior before vs after**  
5. **Tests added/updated**  
6. **Validation commands run and results**  
7. **Any unrelated failures observed**  
8. **Review package** (§10 templates)  
9. **Final status:** `CORRECTIONS_VALIDATED` | `CORRECTIONS_WITH_WARNINGS` | `BLOCKED`

---

## 10. Review package templates

Fill after §6–7. Include **Staged changes** from `git diff --cached --name-status`.

### CORRECTION_SMALL_DIFF

```md
## Review package

Mode: CORRECTION_SMALL_DIFF

Why:
- X changed files
- Y insertions / Z deletions
- Scope limited to requested fixes

Staged changes:
- none
```

or:

```md
Staged changes:
- <files from git diff --cached --name-status>
```

Unstaged / working tree:
- Summarize if different from staged (brief; full diff below).

Commands used:

```bash
git add -N .
git --no-pager status --short
git --no-pager diff --cached --name-status
git --no-pager diff --stat
git --no-pager diff --find-renames --find-copies -U20
```

Paste to reviewer:

- User fix list
- Scope control section
- Git status (short)
- Diff stat
- **Full diff** (`-U20`)
- Tests run + results

Helper artifacts (optional, gitignored): `.review/working-tree-summary.md`, `.review/full.diff`
```

### CORRECTION_LARGE_DIFF

```md
## Review package

Mode: CORRECTION_LARGE_DIFF

Why:
- X changed files
- Y insertions / Z deletions
- Scope spans: <areas>
- Potential scope drift: yes | no

Staged changes:
- none
```

or:

```md
Staged changes:
- <files from git diff --cached --name-status>
```

Commands used:

```bash
git add -N .
git --no-pager status --short
git --no-pager diff --cached --name-status
git --no-pager diff --stat
git --no-pager diff --name-status
git --no-pager diff --numstat
```

Recommended review order:

1. <highest-risk changed file/group — migrations, API, pipeline, persistence>
2. <second-risk group>
3. <tests>
4. <low-risk files — docs, i18n-only, comments>

Next diff commands:

```bash
git --no-pager diff --find-renames --find-copies -U20 -- <path-1>
git --no-pager diff --find-renames --find-copies -U20 -- <path-2>
git --no-pager diff --find-renames --find-copies -U20 -- <path-3>
```

Paste to reviewer first:

- User fix list
- Scope control section
- Git status
- Diff stat
- Name-status
- Numstat summary
- Tests run + results
- Recommended review order + chunk commands

Do **not** paste the entire full diff at once unless the user requests it.

Helper artifacts (optional): `.review/review-plan.md`, `.review/diff-*.diff`
```

---

**NOW EXECUTE**

Apply only the user-provided fixes. Always end with **Scope control** and **Review package** (§8–10).
