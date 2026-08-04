# Git diff review — capture finish Phase 0/1

**Mode:** LARGE_DIFF (20 files, ~955+/43−)

## Recommended review order

1. `mobile/src/features/capture/captureService.ts` + `finishObservability.ts` — finish race + mutex + metrics
2. `mobile/src/database/migrations/migrations.ts` + schema + `markCaptureFrozen`
3. `mobile/src/features/upload/uploadQueue.ts` — obs + debounce
4. `mobile/src/screens/CaptureScreen.tsx` — stage labels
5. Tests + `audit/capture-upload-local/*`

## Chunk commands

```bash
git --no-pager diff --find-renames --find-copies -U20 -- mobile/src/features/capture/
git --no-pager diff --find-renames --find-copies -U20 -- mobile/src/database/
git --no-pager diff --find-renames --find-copies -U20 -- mobile/src/features/upload/uploadQueue.ts
git --no-pager diff --find-renames --find-copies -U20 -- mobile/tests/
```

Full dump: `review/capture-finish-phase0-1-diff.txt` (gitignored).
