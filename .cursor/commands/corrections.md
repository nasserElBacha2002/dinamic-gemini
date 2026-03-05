/corrections

ROLE
You are a senior engineer doing a corrective refactor on an existing feature with strict scope control.

SCOPE
Only touch files needed to implement the listed fixes. Do not refactor unrelated modules.

PROCESS (STRICT)
1) Read the target files and identify exact locations to patch.
2) Propose a minimal patch plan (file-by-file, function-by-function).
3) Apply changes in small commits:
   - First: bbox parsing + UNLOCALIZED fallback correctness.
   - Second: dedupe logic unification + set-based dedupe.
   - Third: evidence_index path contract.
   - Fourth: jobs result mode correctness.
   - Fifth: config output_dir normalization (only if safe).
4) Add/update tests after each logical change.

QUALITY BAR
- Deterministic output.
- No duplicate hashing implementations across modules.
- Evidence index must be self-contained.
- No breaking changes to existing report formats.

OUTPUT
- Provide final diffs (or full file contents if diffs not supported).
- Provide commands to run tests and a quick manual verification checklist.

NOW APPLY THESE FIXES
(Insert the exact fix list from the prompt above.)